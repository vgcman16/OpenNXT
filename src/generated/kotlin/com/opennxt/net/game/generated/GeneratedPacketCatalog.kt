package com.opennxt.net.game.generated

import com.opennxt.net.Side
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import kotlin.reflect.KClass
import com.opennxt.net.game.generated.clientprot.ResumePCountdialogGeneratedPacket
import com.opennxt.net.game.generated.clientprot.WorldlistFetchGeneratedPacket
import com.opennxt.net.game.generated.serverprot.ClientSetvarcLargeGeneratedPacket
import com.opennxt.net.game.generated.serverprot.ClientSetvarcSmallGeneratedPacket
import com.opennxt.net.game.generated.serverprot.ClientSetvarcstrSmallGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfClosesubGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfOpensubActivePlayerGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfOpensubGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfOpentopGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfSetcolourGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfSeteventsGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfSethideGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfSetplayerheadGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfSetplayermodelSelfGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfSetrecolGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfSetscrollposGeneratedPacket
import com.opennxt.net.game.generated.serverprot.IfSettextGeneratedPacket
import com.opennxt.net.game.generated.serverprot.ObjAddGeneratedPacket
import com.opennxt.net.game.generated.serverprot.ObjCountGeneratedPacket
import com.opennxt.net.game.generated.serverprot.ObjDelGeneratedPacket
import com.opennxt.net.game.generated.serverprot.ObjRevealGeneratedPacket
import com.opennxt.net.game.generated.serverprot.UpdateStatGeneratedPacket
import com.opennxt.net.game.generated.serverprot.VarpLargeGeneratedPacket
import com.opennxt.net.game.generated.serverprot.VarpSmallGeneratedPacket

object GeneratedPacketCatalog {
    data class Field(val name: String, val type: String, val kotlinType: String)

    data class Entry(
        val side: Side,
        val name: String,
        val opcode: Int,
        val clazz: KClass<out GamePacket>,
        val codecType: KClass<out DynamicGamePacketCodec<*>>,
        val fields: List<Field>,
        val hasManualRegistration: Boolean,
        val runtimePriority: Boolean
    )

    val entries: List<Entry> = listOf(
        Entry(
            side = Side.CLIENT,
            name = "WORLDLIST_FETCH",
            opcode = 110,
            clazz = WorldlistFetchGeneratedPacket::class,
            codecType = WorldlistFetchGeneratedPacket.Codec::class,
            fields = listOf(Field("checksum", "int", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.CLIENT,
            name = "RESUME_P_COUNTDIALOG",
            opcode = 129,
            clazz = ResumePCountdialogGeneratedPacket::class,
            codecType = ResumePCountdialogGeneratedPacket.Codec::class,
            fields = listOf(Field("count", "long", "Long")),
            hasManualRegistration = false,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "OBJ_REVEAL",
            opcode = 3,
            clazz = ObjRevealGeneratedPacket::class,
            codecType = ObjRevealGeneratedPacket.Codec::class,
            fields = listOf(Field("count", "ushortle", "Int"), Field("id", "ushortle", "Int"), Field("packedCoord", "ubyte", "Int"), Field("playerIndex", "ushortle", "Int")),
            hasManualRegistration = false,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_SETCOLOUR",
            opcode = 8,
            clazz = IfSetcolourGeneratedPacket::class,
            codecType = IfSetcolourGeneratedPacket.Codec::class,
            fields = listOf(Field("component", "intv1", "Int"), Field("colour", "ushort128", "Int")),
            hasManualRegistration = false,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_OPENSUB",
            opcode = 38,
            clazz = IfOpensubGeneratedPacket::class,
            codecType = IfOpensubGeneratedPacket.Codec::class,
            fields = listOf(Field("xtea0", "int", "Int"), Field("parent", "intle", "Int"), Field("xtea1", "int", "Int"), Field("xtea2", "int", "Int"), Field("flag", "u128byte", "Int"), Field("id", "ushortle128", "Int"), Field("xtea3", "int", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_SETHIDE",
            opcode = 45,
            clazz = IfSethideGeneratedPacket::class,
            codecType = IfSethideGeneratedPacket.Codec::class,
            fields = listOf(Field("parent", "int", "Int"), Field("hidden", "u128byte", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_CLOSESUB",
            opcode = 50,
            clazz = IfClosesubGeneratedPacket::class,
            codecType = IfClosesubGeneratedPacket.Codec::class,
            fields = listOf(Field("parent", "int", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "VARP_LARGE",
            opcode = 51,
            clazz = VarpLargeGeneratedPacket::class,
            codecType = VarpLargeGeneratedPacket.Codec::class,
            fields = listOf(Field("value", "int", "Int"), Field("id", "ushort", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_SETTEXT",
            opcode = 57,
            clazz = IfSettextGeneratedPacket::class,
            codecType = IfSettextGeneratedPacket.Codec::class,
            fields = listOf(Field("text", "string", "String"), Field("parent", "intle", "Int")),
            hasManualRegistration = true,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_SETEVENTS",
            opcode = 59,
            clazz = IfSeteventsGeneratedPacket::class,
            codecType = IfSeteventsGeneratedPacket.Codec::class,
            fields = listOf(Field("mask", "intle", "Int"), Field("fromSlot", "ushortle", "Int"), Field("parent", "intv2", "Int"), Field("toSlot", "ushortle128", "Int")),
            hasManualRegistration = true,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "VARP_SMALL",
            opcode = 72,
            clazz = VarpSmallGeneratedPacket::class,
            codecType = VarpSmallGeneratedPacket.Codec::class,
            fields = listOf(Field("id", "ushort", "Int"), Field("value", "ubyte", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_SETPLAYERHEAD",
            opcode = 77,
            clazz = IfSetplayerheadGeneratedPacket::class,
            codecType = IfSetplayerheadGeneratedPacket.Codec::class,
            fields = listOf(Field("component", "intv1", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "OBJ_ADD",
            opcode = 87,
            clazz = ObjAddGeneratedPacket::class,
            codecType = ObjAddGeneratedPacket.Codec::class,
            fields = listOf(Field("count", "ushortle128", "Int"), Field("packedCoord", "ubytec", "Int"), Field("id", "ushort128", "Int")),
            hasManualRegistration = false,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "OBJ_DEL",
            opcode = 98,
            clazz = ObjDelGeneratedPacket::class,
            codecType = ObjDelGeneratedPacket.Codec::class,
            fields = listOf(Field("packedCoord", "u128byte", "Int"), Field("id", "ushort", "Int")),
            hasManualRegistration = false,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_SETPLAYERMODEL_SELF",
            opcode = 106,
            clazz = IfSetplayermodelSelfGeneratedPacket::class,
            codecType = IfSetplayermodelSelfGeneratedPacket.Codec::class,
            fields = listOf(Field("component", "intv2", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_SETSCROLLPOS",
            opcode = 108,
            clazz = IfSetscrollposGeneratedPacket::class,
            codecType = IfSetscrollposGeneratedPacket.Codec::class,
            fields = listOf(Field("component", "intle", "Int"), Field("scrollPosition", "ushort", "Int")),
            hasManualRegistration = false,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_OPENSUB_ACTIVE_PLAYER",
            opcode = 116,
            clazz = IfOpensubActivePlayerGeneratedPacket::class,
            codecType = IfOpensubActivePlayerGeneratedPacket.Codec::class,
            fields = listOf(Field("subInterfaceId", "ushort", "Int"), Field("playerIndex", "ushort128", "Int"), Field("reserved0", "int", "Int"), Field("targetComponent", "intv1", "Int"), Field("reserved1", "long", "Long"), Field("mode", "ubytec", "Int"), Field("reserved2", "int", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "CLIENT_SETVARC_LARGE",
            opcode = 124,
            clazz = ClientSetvarcLargeGeneratedPacket::class,
            codecType = ClientSetvarcLargeGeneratedPacket.Codec::class,
            fields = listOf(Field("id", "ushortle", "Int"), Field("value", "intv1", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_OPENTOP",
            opcode = 126,
            clazz = IfOpentopGeneratedPacket::class,
            codecType = IfOpentopGeneratedPacket.Codec::class,
            fields = listOf(Field("xtea0", "int", "Int"), Field("xtea1", "int", "Int"), Field("xtea2", "int", "Int"), Field("id", "ushortle", "Int"), Field("xtea3", "int", "Int"), Field("bool", "ubyte", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "OBJ_COUNT",
            opcode = 127,
            clazz = ObjCountGeneratedPacket::class,
            codecType = ObjCountGeneratedPacket.Codec::class,
            fields = listOf(Field("packedCoord", "ubyte", "Int"), Field("id", "ushort", "Int"), Field("oldCount", "ushort", "Int"), Field("newCount", "ushort", "Int")),
            hasManualRegistration = false,
            runtimePriority = true
        ),
        Entry(
            side = Side.SERVER,
            name = "CLIENT_SETVARC_SMALL",
            opcode = 128,
            clazz = ClientSetvarcSmallGeneratedPacket::class,
            codecType = ClientSetvarcSmallGeneratedPacket.Codec::class,
            fields = listOf(Field("id", "ushortle", "Int"), Field("value", "ubyte", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "UPDATE_STAT",
            opcode = 129,
            clazz = UpdateStatGeneratedPacket::class,
            codecType = UpdateStatGeneratedPacket.Codec::class,
            fields = listOf(Field("stat", "ubyte", "Int"), Field("level", "u128byte", "Int"), Field("experience", "int", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "CLIENT_SETVARCSTR_SMALL",
            opcode = 130,
            clazz = ClientSetvarcstrSmallGeneratedPacket::class,
            codecType = ClientSetvarcstrSmallGeneratedPacket.Codec::class,
            fields = listOf(Field("value", "string", "String"), Field("id", "ushort", "Int")),
            hasManualRegistration = true,
            runtimePriority = false
        ),
        Entry(
            side = Side.SERVER,
            name = "IF_SETRECOL",
            opcode = 202,
            clazz = IfSetrecolGeneratedPacket::class,
            codecType = IfSetrecolGeneratedPacket.Codec::class,
            fields = listOf(Field("value0", "ushortle", "Int"), Field("value1", "ushortle", "Int"), Field("value2", "ubytec", "Int"), Field("value3", "intle", "Int")),
            hasManualRegistration = false,
            runtimePriority = false
        )
    )

    fun registerAll() {
        PacketRegistry.registerInspectionGenerated(Side.CLIENT, "RESUME_P_COUNTDIALOG", ResumePCountdialogGeneratedPacket::class, ResumePCountdialogGeneratedPacket.Codec::class)
        PacketRegistry.registerInspectionGenerated(Side.SERVER, "OBJ_REVEAL", ObjRevealGeneratedPacket::class, ObjRevealGeneratedPacket.Codec::class)
        PacketRegistry.registerInspectionGenerated(Side.SERVER, "IF_SETCOLOUR", IfSetcolourGeneratedPacket::class, IfSetcolourGeneratedPacket.Codec::class)
        PacketRegistry.registerInspectionGenerated(Side.SERVER, "OBJ_ADD", ObjAddGeneratedPacket::class, ObjAddGeneratedPacket.Codec::class)
        PacketRegistry.registerInspectionGenerated(Side.SERVER, "OBJ_DEL", ObjDelGeneratedPacket::class, ObjDelGeneratedPacket.Codec::class)
        PacketRegistry.registerInspectionGenerated(Side.SERVER, "IF_SETSCROLLPOS", IfSetscrollposGeneratedPacket::class, IfSetscrollposGeneratedPacket.Codec::class)
        PacketRegistry.registerInspectionGenerated(Side.SERVER, "OBJ_COUNT", ObjCountGeneratedPacket::class, ObjCountGeneratedPacket.Codec::class)
        PacketRegistry.registerInspectionGenerated(Side.SERVER, "IF_SETRECOL", IfSetrecolGeneratedPacket::class, IfSetrecolGeneratedPacket.Codec::class)
    }
}
