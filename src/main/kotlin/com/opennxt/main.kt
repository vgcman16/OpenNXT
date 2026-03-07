package com.opennxt

import com.github.ajalt.clikt.core.Context
import com.github.ajalt.clikt.core.NoOpCliktCommand
import com.github.ajalt.clikt.core.main
import com.github.ajalt.clikt.core.subcommands
import com.opennxt.tools.ToolExecutor

fun main(args: Array<String>) {
    val root = object : NoOpCliktCommand(name = "open-nxt") {
        override fun help(context: Context): String = "Base command for the OpenNXT server"
    }

    root.subcommands(OpenNXT, ToolExecutor).main(args)
}
