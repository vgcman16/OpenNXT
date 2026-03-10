package com.opennxt.login

import com.opennxt.net.GenericResponse
import mu.KotlinLogging
import java.util.*

enum class LoginResult(val code: GenericResponse) {
    SUCCESS(GenericResponse.SUCCESSFUL),
    FAILED_LOADING(GenericResponse.FAILED_LOADING_PROFILE),
    DATABASE_TIMEOUT(GenericResponse.LOGINSERVER_OFFLINE),
    DATABASE_ERROR(GenericResponse.INVALID_LOGIN_SERVER_RESPONSE),
    INVALID_USERNAME_PASS(GenericResponse.INVALID_USERNAME_OR_PASSWORD),
    WORLD_FULL(GenericResponse.WORLD_FULL),
    DISABLED(GenericResponse.DISABLED_ACCOUNT),
    LOCKED(GenericResponse.ACCOUNT_LOCKED),
    LOGIN_ATTEMPTS_EXCEEDED(GenericResponse.LOGIN_ATTEMPTS_EXCEEDED),
    LOGIN_PREVENTED(GenericResponse.LOGIN_PREVENTED),
    SESSION_EXPIRED(GenericResponse.SESSION_EXPIRED),
    SESSION_ENDED(GenericResponse.SESSION_ENDED),
    ACCOUNT_INACCESSIBLE(GenericResponse.ACCOUNT_INACCESSIBLE),
    AUTHENTICATOR_CODE(GenericResponse.AUTHENTICATOR_CODE),
    AUTHENTICATOR_INCORRECT(GenericResponse.AUTHENTICATOR_INCORRECT),
    BANNED(GenericResponse.TEMPORARILY_BANNED),
    LOGGED_IN(GenericResponse.LOGGED_IN),
    OUT_OF_DATE(GenericResponse.OUT_OF_DATE),
    ;

    companion object {
        private val logger = KotlinLogging.logger {  }

        private val REVERSE_LOOKUP = EnumMap<GenericResponse, LoginResult>(GenericResponse::class.java)

        init {
            values().forEach { res -> REVERSE_LOOKUP[res.code] = res }
        }

        fun reverse(response: GenericResponse): LoginResult {
            val reversed = REVERSE_LOOKUP[response]
            if (reversed != null)
                return reversed
            logger.warn { "Couldn't find GenericResponse->LoginResult mapping for $response, returning DATABASE_ERROR" }
            return DATABASE_ERROR
        }
    }
}
