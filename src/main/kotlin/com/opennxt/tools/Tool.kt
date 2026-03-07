package com.opennxt.tools

import com.github.ajalt.clikt.core.CliktCommand
import com.github.ajalt.clikt.core.Context
import com.opennxt.Constants
import com.opennxt.filesystem.Filesystem
import com.opennxt.filesystem.sqlite.SqliteFilesystem
import com.opennxt.resources.FilesystemResources
import mu.KotlinLogging

abstract class Tool(name: String, private val commandHelp: String) : CliktCommand(name = name) {
    protected val logger = KotlinLogging.logger { }

    override fun help(context: Context): String = commandHelp

    protected val filesystem by lazy {
        logger.info { "Loading filesystem from ${Constants.CACHE_PATH}" }
        SqliteFilesystem(Constants.CACHE_PATH)
    }

    protected val resources by lazy {
        logger.info { "Loading filesystem resources" }
        FilesystemResources(filesystem, Constants.RESOURCE_PATH)
    }

    override fun run() {
        logger.info { "Executing tool ${this::class.simpleName}" }

        runTool()
    }

    abstract fun runTool()

}
