package com.opennxt.net.login

import com.opennxt.OpenNXT
import com.opennxt.config.RsaConfig
import com.opennxt.ext.decipherXtea
import com.opennxt.ext.readBuild
import com.opennxt.ext.readString
import com.opennxt.model.entity.PlayerEntity
import com.opennxt.model.world.TileLocation
import com.opennxt.model.world.WorldPlayer
import com.opennxt.net.GenericResponse
import com.opennxt.net.RSChannelAttributes
import com.opennxt.net.login.LoginRSAHeader.Companion.readLoginHeader
import io.netty.buffer.ByteBuf
import io.netty.buffer.Unpooled
import io.netty.channel.ChannelFutureListener
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import mu.KotlinLogging
import java.math.BigInteger
import kotlin.system.exitProcess

class LoginServerDecoder(val rsaPair: RsaConfig.RsaKeyPair) : ByteToMessageDecoder() {
    private val logger = KotlinLogging.logger { }

    private fun logGameAltDiagnostics(remote: Any, bytes: ByteArray, cause: Exception? = null) {
        val fullHex = bytes.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
        logger.warn { "GAME_ALT diagnostic for $remote: payloadLength=${bytes.size}, payload=$fullHex" }
        if (cause != null) {
            logger.warn(cause) { "GAME_ALT parse failed for $remote, scanning candidate RSA slices" }
        }

        val candidates = mutableListOf<String>()
        for (start in 0 until minOf(bytes.size, 12)) {
            for (size in 64..(bytes.size - start)) {
                val raw = bytes.copyOfRange(start, start + size)
                val decrypted = try {
                    BigInteger(raw).modPow(rsaPair.exponent, rsaPair.modulus).toByteArray()
                } catch (_: Exception) {
                    continue
                }
                if (decrypted.isNotEmpty() && (decrypted[0].toInt() and 0xff) == 10) {
                    val preview = decrypted.take(16).joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
                    candidates += "start=$start size=$size preview=$preview"
                }
            }
        }

        if (candidates.isEmpty()) {
            logger.warn { "GAME_ALT diagnostic for $remote: no candidate RSA slices produced magic 10" }
        } else {
            candidates.forEach { logger.warn { "GAME_ALT candidate for $remote: $it" } }
        }
    }

    private fun decodeGameAlt(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        if (buf.readableBytes() < 3) {
            logger.info {
                "Login decoder waiting for GAME_ALT header from ${ctx.channel().remoteAddress()} " +
                    "readable=${buf.readableBytes()}"
            }
            buf.resetReaderIndex()
            return
        }

        val control = buf.readUnsignedByte().toInt()
        val length = buf.readUnsignedShort()
        if (buf.readableBytes() < length) {
            logger.info {
                "Login decoder waiting for GAME_ALT payload from ${ctx.channel().remoteAddress()} " +
                    "control=$control, length=$length, readable=${buf.readableBytes()}"
            }
            buf.resetReaderIndex()
            return
        }

        ctx.channel().attr(RSChannelAttributes.LOGIN_TYPE).set(LoginType.GAME_ALT)

        val payload = buf.readBytes(length)
        val payloadBytes = ByteArray(length)
        payload.getBytes(payload.readerIndex(), payloadBytes)
        try {
            if (payload.readableBytes() < 4) {
                throw IllegalStateException("GAME_ALT payload too short: ${payload.readableBytes()} bytes")
            }

            val reconnectFlag = payload.readUnsignedByte().toInt()
            val auxiliary = payload.readUnsignedByte().toInt()
            val rsaSize = payload.readUnsignedShort()
            if (payload.readableBytes() < rsaSize) {
                throw IllegalStateException(
                    "GAME_ALT RSA block truncated: expected $rsaSize bytes, got ${payload.readableBytes()}"
                )
            }

            val syntheticHeader = Unpooled.buffer(1 + 2 + rsaSize)
            val header = try {
                syntheticHeader.writeByte(reconnectFlag)
                syntheticHeader.writeShort(rsaSize)
                syntheticHeader.writeBytes(payload, rsaSize)
                syntheticHeader.readerIndex(0)
                syntheticHeader.readLoginHeader(LoginType.GAME_ALT, rsaPair.exponent, rsaPair.modulus)
            } catch (primary: Exception) {
                payload.readerIndex(1)
                val fallbackRsaSize = payload.readUnsignedMedium()
                if (payload.readableBytes() < fallbackRsaSize) {
                    throw primary
                }

                syntheticHeader.clear()
                syntheticHeader.writeByte(reconnectFlag)
                syntheticHeader.writeShort(fallbackRsaSize)
                syntheticHeader.writeBytes(payload, fallbackRsaSize)
                syntheticHeader.readerIndex(0)
                syntheticHeader.readLoginHeader(LoginType.GAME_ALT, rsaPair.exponent, rsaPair.modulus)
            } finally {
                syntheticHeader.release()
            }

            val snapshot = LoginHandoffStore.recall(ctx.channel().remoteAddress())
                ?: throw IllegalStateException("No stored lobby login snapshot for ${ctx.channel().remoteAddress()}")

            if (header.uniqueId != ctx.channel().attr(RSChannelAttributes.LOGIN_UNIQUE_ID).get()) {
                logger.error { "Unique id mismatch on GAME_ALT - possible replay attack?" }
                ctx.channel()
                    .writeAndFlush(LoginPacket.LoginResponse(GenericResponse.MALFORMED_PACKET))
                    .addListener(ChannelFutureListener.CLOSE)
                return
            }

            if (payload.isReadable) {
                logger.warn {
                    "GAME_ALT payload for ${ctx.channel().remoteAddress()} still had ${payload.readableBytes()} trailing bytes"
                }
            }

            ctx.channel().attr(RSChannelAttributes.LOGIN_USERNAME).set(snapshot.username)

            logger.info {
                "Attempted game alt login: ${snapshot.username}, ***** " +
                    "(control=$control, reconnect=$reconnectFlag, aux=$auxiliary, payloadLength=$length, rsaSize=$rsaSize)"
            }
            out.add(
                LoginPacket.GameLoginRequest(
                    snapshot.build,
                    header,
                    snapshot.username,
                    snapshot.password,
                    Unpooled.wrappedBuffer(snapshot.remaining.copyOf())
                )
            )
        } catch (e: Exception) {
            logGameAltDiagnostics(ctx.channel().remoteAddress(), payloadBytes, e)
            e.printStackTrace()
            ctx.channel()
                .writeAndFlush(LoginPacket.LoginResponse(GenericResponse.MALFORMED_PACKET))
                .addListener(ChannelFutureListener.CLOSE)
        } finally {
            payload.release()
        }
    }

    override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        buf.markReaderIndex()
        val entryPreviewLength = minOf(buf.readableBytes(), 32)
        val entryPreview = ByteArray(entryPreviewLength)
        buf.getBytes(buf.readerIndex(), entryPreview)
        val entryPreviewHex = entryPreview.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
        logger.info {
            "Login decoder entry from ${ctx.channel().remoteAddress()}: readable=${buf.readableBytes()}, " +
                "preview=$entryPreviewHex"
        }

        val id = buf.readUnsignedByte().toInt()
        val type = LoginType.fromId(id)
        if (type == null) {
            val previewLength = minOf(buf.readableBytes(), 32)
            val preview = ByteArray(previewLength)
            buf.getBytes(buf.readerIndex(), preview)
            val previewHex = preview.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
            logger.warn(
                "Client from ${ctx.channel().remoteAddress()} attempted to login with unknown id: $id " +
                    "(remaining=${buf.readableBytes()}, preview=$previewHex)"
            )
            buf.skipBytes(buf.readableBytes())
            ctx.close()
            return
        }

        // TODO Move this to another decoder or something, this should *probably* not be here.
        if (type == LoginType.GAMELOGIN_CONTINUE) {
            if (ctx.channel().attr(RSChannelAttributes.LOGIN_TYPE).get() == null) {
                logger.error { "GAMELOGIN_CONTINUE sent from client that is not in login state" }
                buf.skipBytes(buf.readableBytes())
                ctx.channel().close()
                return
            }

            if (ctx.channel().attr(RSChannelAttributes.PASSTHROUGH_CHANNEL).get() == null) {
                logger.info { "TODO: Send game login response" }

                OpenNXT.world.addPlayer(
                    WorldPlayer(
                        ctx.channel().attr(RSChannelAttributes.CONNECTED_CLIENT).get(),
                        ctx.channel().attr(RSChannelAttributes.LOGIN_USERNAME).get(),
                        PlayerEntity(TileLocation(3222, 3222, 0))
                    )
                )
                // TODO Send login response here? Why are we doing this here...
            }
            return
        }

        if (type == LoginType.GAME_ALT) {
            decodeGameAlt(ctx, buf, out)
            return
        }

        if (buf.readableBytes() < 2) {
            logger.info {
                "Login decoder waiting for length bytes from ${ctx.channel().remoteAddress()} " +
                    "after type=$type, readable=${buf.readableBytes()}"
            }
            buf.resetReaderIndex()
            return
        }

        val length = buf.readUnsignedShort()
        if (buf.readableBytes() < length) {
            logger.info {
                "Login decoder waiting for payload from ${ctx.channel().remoteAddress()} " +
                    "after type=$type, length=$length, readable=${buf.readableBytes()}"
            }
            buf.resetReaderIndex()
            return
        }

        ctx.channel().attr(RSChannelAttributes.LOGIN_TYPE).set(type)

        val payload = buf.readBytes(length)
        try {
            val build = payload.readBuild()
            val header = payload.readLoginHeader(type, rsaPair.exponent, rsaPair.modulus)

            if (header !is LoginRSAHeader.Fresh && type != LoginType.LOBBY) {
                logger.info { "got reconnecting block in lobby? what?" } // literally impossible but ok.
                ctx.channel()
                    .writeAndFlush(LoginPacket.LoginResponse(GenericResponse.MALFORMED_PACKET))
                    .addListener(ChannelFutureListener.CLOSE)
                return
            }

            payload.decipherXtea(header.seeds)

            payload.markReaderIndex()
            val original = ByteArray(payload.readableBytes())
            payload.readBytes(original)
            payload.resetReaderIndex()

            payload.skipBytes(1) // TODO This has to do with name being encoded as long, should prolly check it
            val name = payload.readString()

            ctx.channel().attr(RSChannelAttributes.LOGIN_USERNAME).set(name)
            if (header.uniqueId != ctx.channel().attr(RSChannelAttributes.LOGIN_UNIQUE_ID).get()) {
                logger.error { "Unique id mismatch - possible replay attack?" }
                ctx.channel()
                    .writeAndFlush(LoginPacket.LoginResponse(GenericResponse.MALFORMED_PACKET))
                    .addListener(ChannelFutureListener.CLOSE)
                return
            }

            when (type) {
                LoginType.LOBBY -> {
                    header as LoginRSAHeader.Fresh

                    logger.info { "Attempted lobby login: $name, *****" }
                    out.add(
                        LoginPacket.LobbyLoginRequest(
                            build,
                            header,
                            name,
                            header.password,
                            Unpooled.wrappedBuffer(original)
                        )
                    )
                }
                LoginType.GAME, LoginType.GAME_ALT -> {
                    if (header !is LoginRSAHeader.Fresh) {
                        logger.warn { "Client attempted to reconnect, this isn't supported yet!" }
                        ctx.channel()
                            .writeAndFlush(LoginPacket.LoginResponse(GenericResponse.LOGINSERVER_REJECTED))
                            .addListener(ChannelFutureListener.CLOSE)
                        return
                    }

                    logger.info { "Attempted game login: $name, ***** (type=$type)" }
                    out.add(
                        LoginPacket.GameLoginRequest(
                            build,
                            header,
                            name,
                            header.password,
                            Unpooled.wrappedBuffer(original)
                        )
                    )
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
            ctx.channel()
                .writeAndFlush(LoginPacket.LoginResponse(GenericResponse.MALFORMED_PACKET))
                .addListener(ChannelFutureListener.CLOSE)
        } finally {
            payload.release()
        }
    }
}
