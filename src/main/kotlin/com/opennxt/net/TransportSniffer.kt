package com.opennxt.net

import io.netty.buffer.ByteBuf
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import io.netty.handler.ssl.SslContext
import mu.KotlinLogging
import java.net.InetSocketAddress
import kotlin.math.min

class TransportSniffer(private val tlsContext: SslContext) : ByteToMessageDecoder() {
    private val logger = KotlinLogging.logger {}

    init {
        isSingleDecode = true
    }

    private data class TlsClientHelloInfo(
        val serverName: String?,
        val alpnProtocols: List<String>,
        val supportedVersions: List<String>,
    )

    private fun formatTlsVersion(major: Int, minor: Int): String {
        return when ((major shl 8) or minor) {
            0x0300 -> "SSLv3"
            0x0301 -> "TLSv1.0"
            0x0302 -> "TLSv1.1"
            0x0303 -> "TLSv1.2"
            0x0304 -> "TLSv1.3"
            else -> "0x${major.toString(16).padStart(2, '0')}${minor.toString(16).padStart(2, '0')}"
        }
    }

    // Parse the first ClientHello record so we can see which host the native client expects on the TLS hop.
    private fun parseTlsClientHello(buf: ByteBuf, readerIndex: Int): TlsClientHelloInfo? {
        if (buf.readableBytes() < 5) {
            return null
        }

        val recordLength = buf.getUnsignedShort(readerIndex + 3).toInt()
        val recordEnd = readerIndex + 5 + recordLength
        if (buf.writerIndex() < recordEnd) {
            return null
        }

        val handshakeType = buf.getUnsignedByte(readerIndex + 5).toInt()
        if (handshakeType != 0x01) {
            return null
        }

        val handshakeLength = buf.getUnsignedMedium(readerIndex + 6)
        val handshakeStart = readerIndex + 9
        val handshakeEnd = min(recordEnd, handshakeStart + handshakeLength)
        var offset = handshakeStart

        fun requireAvailable(length: Int): Boolean = offset + length <= handshakeEnd

        if (!requireAvailable(2 + 32)) {
            return null
        }
        offset += 2 + 32

        if (!requireAvailable(1)) {
            return null
        }
        val sessionIdLength = buf.getUnsignedByte(offset).toInt()
        offset += 1
        if (!requireAvailable(sessionIdLength)) {
            return null
        }
        offset += sessionIdLength

        if (!requireAvailable(2)) {
            return null
        }
        val cipherSuitesLength = buf.getUnsignedShort(offset).toInt()
        offset += 2
        if (!requireAvailable(cipherSuitesLength)) {
            return null
        }
        offset += cipherSuitesLength

        if (!requireAvailable(1)) {
            return null
        }
        val compressionMethodsLength = buf.getUnsignedByte(offset).toInt()
        offset += 1
        if (!requireAvailable(compressionMethodsLength)) {
            return null
        }
        offset += compressionMethodsLength

        if (!requireAvailable(2)) {
            return TlsClientHelloInfo(serverName = null, alpnProtocols = emptyList(), supportedVersions = emptyList())
        }
        val extensionsLength = buf.getUnsignedShort(offset).toInt()
        offset += 2
        val extensionsEnd = min(handshakeEnd, offset + extensionsLength)

        var serverName: String? = null
        val alpnProtocols = mutableListOf<String>()
        val supportedVersions = mutableListOf<String>()

        while (offset + 4 <= extensionsEnd) {
            val extensionType = buf.getUnsignedShort(offset).toInt()
            val extensionLength = buf.getUnsignedShort(offset + 2).toInt()
            offset += 4
            if (offset + extensionLength > extensionsEnd) {
                break
            }

            when (extensionType) {
                0x0000 -> {
                    if (extensionLength >= 5) {
                        val listLength = buf.getUnsignedShort(offset).toInt()
                        var nameOffset = offset + 2
                        val nameEnd = min(offset + 2 + listLength, offset + extensionLength)
                        while (nameOffset + 3 <= nameEnd) {
                            val nameType = buf.getUnsignedByte(nameOffset).toInt()
                            val nameLength = buf.getUnsignedShort(nameOffset + 1).toInt()
                            nameOffset += 3
                            if (nameOffset + nameLength > nameEnd) {
                                break
                            }
                            if (nameType == 0) {
                                serverName = buf.toString(nameOffset, nameLength, Charsets.US_ASCII)
                                break
                            }
                            nameOffset += nameLength
                        }
                    }
                }

                0x0010 -> {
                    if (extensionLength >= 2) {
                        val listLength = buf.getUnsignedShort(offset).toInt()
                        var protoOffset = offset + 2
                        val protoEnd = min(offset + 2 + listLength, offset + extensionLength)
                        while (protoOffset + 1 <= protoEnd) {
                            val protoLength = buf.getUnsignedByte(protoOffset).toInt()
                            protoOffset += 1
                            if (protoOffset + protoLength > protoEnd) {
                                break
                            }
                            alpnProtocols += buf.toString(protoOffset, protoLength, Charsets.US_ASCII)
                            protoOffset += protoLength
                        }
                    }
                }

                0x002b -> {
                    if (extensionLength >= 1) {
                        val listLength = buf.getUnsignedByte(offset).toInt()
                        var versionOffset = offset + 1
                        val versionEnd = min(offset + 1 + listLength, offset + extensionLength)
                        while (versionOffset + 2 <= versionEnd) {
                            val encodedVersion = buf.getUnsignedShort(versionOffset).toInt()
                            supportedVersions += formatTlsVersion(
                                major = encodedVersion shr 8,
                                minor = encodedVersion and 0xff
                            )
                            versionOffset += 2
                        }
                    }
                }
            }

            offset += extensionLength
        }

        return TlsClientHelloInfo(
            serverName = serverName,
            alpnProtocols = alpnProtocols,
            supportedVersions = supportedVersions,
        )
    }

    override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        if (!buf.isReadable) {
            return
        }

        val readerIndex = buf.readerIndex()
        val contentType = buf.getUnsignedByte(readerIndex).toInt()
        val localPort = (ctx.channel().localAddress() as? InetSocketAddress)?.port ?: -1

        if (contentType == 0x16) {
            if (buf.readableBytes() < 3) {
                return
            }

            val major = buf.getUnsignedByte(readerIndex + 1).toInt()
            val minor = buf.getUnsignedByte(readerIndex + 2).toInt()
            val isTls = major == 0x03 && minor in 0x00..0x04
            if (!isTls) {
                logger.info {
                    "Detected plaintext transport from ${ctx.channel().remoteAddress()} " +
                        "to port $localPort (leading 0x16 was not TLS)"
                }
                ctx.pipeline().remove(this)
                out.add(buf.readRetainedSlice(buf.readableBytes()))
                return
            }

            val hello = parseTlsClientHello(buf, readerIndex)
            logger.info {
                "Detected TLS ClientHello from ${ctx.channel().remoteAddress()} " +
                    "to port $localPort " +
                    "(sni=${hello?.serverName ?: "unknown"}, " +
                    "alpn=${hello?.alpnProtocols?.joinToString(",").orEmpty().ifEmpty { "none" }}, " +
                    "versions=${hello?.supportedVersions?.joinToString(",").orEmpty().ifEmpty { "unknown" }})"
            }
            ctx.pipeline().addAfter(ctx.name(), "tls-server", tlsContext.newHandler(ctx.alloc()))
        } else {
            logger.info {
                "Detected plaintext transport from ${ctx.channel().remoteAddress()} " +
                    "to port $localPort"
            }
        }

        ctx.pipeline().remove(this)
        out.add(buf.readRetainedSlice(buf.readableBytes()))
    }
}
