package com.opennxt.tools

import com.github.ajalt.clikt.core.Context
import com.github.ajalt.clikt.core.NoOpCliktCommand
import com.github.ajalt.clikt.core.subcommands
import io.github.classgraph.ClassGraph
import mu.KotlinLogging
import kotlin.system.exitProcess

object ToolExecutor : NoOpCliktCommand(name = "run-tool") {
    private val logger = KotlinLogging.logger {}

    override fun help(context: Context): String = "Executes a bundled tool in the vgcman16 OpenNXT fork"

    init {
        val result = ClassGraph()
            .enableClassInfo()
            .acceptPackages("com.opennxt.tools.impl")
            .scan()

        val classes = result.getSubclasses("com.opennxt.tools.Tool")

        val tools = classes.map { it.loadClass().getDeclaredConstructor().newInstance() as Tool }

        if (tools.isEmpty()) {
            logger.error { "No bundled tools found" }
            exitProcess(1)
        }

        subcommands(tools)
    }

}
