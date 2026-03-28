package com.opennxt.filesystem

class Index private constructor() {
    companion object {
        const val ANIMS = 0
        const val BASES = 1
        const val CONFIG = 2
        const val INTERFACES = 3
        const val MAPS = 5
        const val MODELS = 7
        const val SPRITES = 8
        const val BINARY = 10
        const val CLIENTSCRIPTS = 12
        const val FONTMETRICS = 13
        const val VORBIS = 14
        const val CONFIG_OBJECT = 16
        const val CONFIG_ENUM = 17
        const val CONFIG_NPC = 18
        const val CONFIG_ITEM = 19
        const val CONFIG_SEQ = 20
        const val CONFIG_SPOT = 21
        const val CONFIG_STRUCT = 22
        const val WORLDMAP = 23
        const val QUICKCHAT = 24
        const val QUICKCHAT_GLOBAL = 25
        const val MATERIALS = 26
        const val PARTICLES = 27
        const val DEFAULTS = 28
        const val BILLBOARDS = 29
        const val DLLS = 30
        const val SHADERS = 31
        const val LOADINGSPRITES = 32
        const val LOADINGSCREENS = 33
        const val LOADINGSPRITESRAW = 34
        const val CUTSCENES = 35
        const val AUDIOSTREAMS = 40
        const val WORLDMAPAREAS = 41
        const val WORLDMAPLABELS = 42
        const val MODELS_RT7 = 47
        const val ANIMS_RT7 = 48
        const val DBTABLEINDEX = 49

        fun nameOf(index: Int): String = when (index) {
            ANIMS -> "ANIMS"
            BASES -> "BASES"
            CONFIG -> "CONFIG"
            INTERFACES -> "INTERFACES"
            MAPS -> "MAPS"
            MODELS -> "MODELS"
            SPRITES -> "SPRITES"
            BINARY -> "BINARY"
            CLIENTSCRIPTS -> "CLIENTSCRIPTS"
            FONTMETRICS -> "FONTMETRICS"
            VORBIS -> "VORBIS"
            CONFIG_OBJECT -> "CONFIG_OBJECT"
            CONFIG_ENUM -> "CONFIG_ENUM"
            CONFIG_NPC -> "CONFIG_NPC"
            CONFIG_ITEM -> "CONFIG_ITEM"
            CONFIG_SEQ -> "CONFIG_SEQ"
            CONFIG_SPOT -> "CONFIG_SPOT"
            CONFIG_STRUCT -> "CONFIG_STRUCT"
            WORLDMAP -> "WORLDMAP"
            QUICKCHAT -> "QUICKCHAT"
            QUICKCHAT_GLOBAL -> "QUICKCHAT_GLOBAL"
            MATERIALS -> "MATERIALS"
            PARTICLES -> "PARTICLES"
            DEFAULTS -> "DEFAULTS"
            BILLBOARDS -> "BILLBOARDS"
            DLLS -> "DLLS"
            SHADERS -> "SHADERS"
            LOADINGSPRITES -> "LOADINGSPRITES"
            LOADINGSCREENS -> "LOADINGSCREENS"
            LOADINGSPRITESRAW -> "LOADINGSPRITESRAW"
            CUTSCENES -> "CUTSCENES"
            AUDIOSTREAMS -> "AUDIOSTREAMS"
            WORLDMAPAREAS -> "WORLDMAPAREAS"
            WORLDMAPLABELS -> "WORLDMAPLABELS"
            MODELS_RT7 -> "MODELS_RT7"
            ANIMS_RT7 -> "ANIMS_RT7"
            DBTABLEINDEX -> "DBTABLEINDEX"
            else -> "INDEX_$index"
        }
    }
}
