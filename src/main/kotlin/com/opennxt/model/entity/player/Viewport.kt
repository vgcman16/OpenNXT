package com.opennxt.model.entity.player

import com.opennxt.OpenNXT
import com.opennxt.model.entity.PlayerEntity
import com.opennxt.model.entity.movement.MovementSpeed
import com.opennxt.model.world.MapSize
import com.opennxt.model.world.TileLocation
import com.opennxt.model.world.WorldPlayer
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.game.serverprot.RebuildNormal

class Viewport(val player: WorldPlayer) {
    val localPlayers = arrayOfNulls<PlayerEntity>(2048)
    val localPlayerIndices = IntArray(2048)
    var localPlayerIndicesCount = 0
    val outPlayerIndices = IntArray(2048)
    var outPlayerIndicesCount = 0
    val regionHashes = IntArray(2048)
    val slotFlags = ByteArray(2048)
    val movementTypes = ByteArray(2048)
    var localAddedPlayers = 0
    val cachedAppearanceHashes = arrayOfNulls<ByteArray>(2048)
    val cachedHeadIconHashes = arrayOfNulls<ByteArray>(2048)

    //    val regions = ObjectOpenHashSet<Region>()
    var sceneRadius = 7
    var baseTile = player.entity.location
    var playerViewingDistance = 14
    // The scene math is standard 104, but 946 expects the historical compat wire id.
    var mapSize = MapSize.SIZE_104

    fun init(buf: GamePacketBuilder) {
        val entity = player.entity

        baseTile = entity.location
        if (entity.index < 1 || entity.index >= 2048)
            throw IllegalStateException("Player index must be between 1 and 2047 for ${player.name}: $player.index")

        buf.switchToBitAccess()
        buf.putBits(30, entity.location.tileHash)

        localPlayers[entity.index] = entity
        localPlayerIndicesCount = 0
        outPlayerIndicesCount = 0
        localPlayerIndices[localPlayerIndicesCount++] = entity.index
        for (index in 1 until 2048) {
            if (index == entity.index)
                continue
            val other = OpenNXT.world.getPlayer(index)
            val speed = other?.movement?.currentSpeed ?: MovementSpeed.STATIONARY
            val hash = (other?.location?.regionHash ?: 0) or (speed.id shl 18)
            buf.putBits(20, hash)
            regionHashes[index] = hash
            outPlayerIndices[outPlayerIndicesCount++] = index
            if (speed != MovementSpeed.STATIONARY)
                continue
            slotFlags[index] = (slotFlags[index].toInt() or 0x1).toByte()
        }
        buf.switchToByteAccess()
        moveToRegion(entity.location, mapSize, false)
    }
    /*
    public void init(GamePacketBuilder buffer) {
        buffer.switchToBitAccess();
        buffer.putBits(30, player.getTileHash());
        localPlayers[player.getIndex()] = player;
        localPlayersIndexes[localPlayersIndexesCount++] = player.getIndex();
        for (int playerIndex = 1; playerIndex < 2048; playerIndex++) {
            if (playerIndex == player.getIndex())
                continue;
            Player player = World.getPlayers().get(playerIndex);
            MovementSpeed speed = MovementSpeed.STATIONARY;
            int hash = 0;
            if (player != null) {
                speed = player.getMovementSpeed();
                hash = player.getRegionHash() | (speed.getId() << 18);
            }
            buffer.putBits(20, regionHashes[playerIndex] = hash);
            outPlayersIndexes[outPlayersIndexesCount++] = playerIndex;
            if (speed != MovementSpeed.STATIONARY) continue;
            slotFlags[playerIndex] = (byte)(slotFlags[playerIndex] | 1);
        }
        buffer.switchToByteAccess();
    }
     */

    fun moveToRegion(tile: TileLocation, size: MapSize, sendUpdate: Boolean = true) {
        this.mapSize = size
        this.baseTile = tile

//        val oldRegions = ObjectOpenHashSet<Region>(regions)
//        regions.clear()

//        for (x in (tile.chunkX - (size.size shr 4)) / 8..(tile.chunkX + (size.size shr 4)) / 8) {
//            for (y in (tile.chunkY - (size.size shr 4)) / 8..(tile.chunkY + (size.size shr 4)) / 8) {
//                try {
//                    val id = (x shl 8) or y
//                    if (id < 0 || id > 65535) continue
//
//                    val region = GameServer.instance.world.regions.getRegion((x shl 8) + y, true)
//                    regions.add(region)
//                    region.addPlayer(player)
//                } catch (e: NullPointerException) {
//                }
//            }
//        }

//        oldRegions.filter { !regions.contains(it) }.forEach { it.removePlayer(player) }

        if (sendUpdate) {
            player.client.write(createPacket())
        }
    }

    fun createPacket(): RebuildNormal {
        val bootstrap = OpenNXT.config.lobbyBootstrap
        return RebuildNormal(
            unused1 = 0,
            chunkX = baseTile.chunkX,
            unused2 = 0,
            chunkY = baseTile.chunkY,
            npcBits = sceneRadius,
            mapSize = mapSize.rebuildWireId(OpenNXT.config.build),
            areaType = bootstrap.rebuildNormalAreaType,
            hash1 = bootstrap.rebuildNormalHash1,
            hash2 = bootstrap.rebuildNormalHash2,
        )
    }

    fun resetForNextTransmit() {
        localPlayerIndicesCount = 0
        outPlayerIndicesCount = 0
        localAddedPlayers = 0
        for (idx in 1 until 2048) {
            slotFlags[idx] = (slotFlags[idx].toInt() shr 1).toByte()
            val player = localPlayers[idx]
            if (player == null)
                outPlayerIndices[outPlayerIndicesCount++] = idx
            else
                localPlayerIndices[localPlayerIndicesCount++] = idx
        }
    }
}
