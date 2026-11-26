package com.jv.audiobox

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/** Ce que la box dit d'elle-même (GET /api/public/state). */
data class Etat(
    val joue: Boolean = false,
    val enPause: Boolean = false,
    val arrete: Boolean = true,
    val position: Double = 0.0,
    val duree: Double = 0.0,
    val volume: Int = 80,
    val titre: String = "",
    val auteur: String = "",
    val origine: String = "",
    val image: String = "",
    val radios: List<String> = emptyList(),
    val sommeil: Int = 0,
    val vitesse: Double = 1.0,
    /** Quand tout est arrêté : ce que « Lecture » relancerait (dernière écoute). */
    val dernier: String = "",
) {
    val estUnLivre: Boolean get() = origine == "abs" || origine == "podcast"

    companion object {
        fun lire(o: JSONObject): Etat {
            val r = o.optJSONArray("radios")
            return Etat(
                joue = o.optBoolean("playing"),
                enPause = o.optBoolean("paused"),
                arrete = o.optBoolean("stopped", true),
                position = o.optDouble("position", 0.0),
                duree = o.optDouble("duration", 0.0),
                volume = o.optInt("volume", 80),
                titre = o.optString("title"),
                auteur = o.optString("author"),
                origine = o.optString("source"),
                image = o.optString("image"),
                radios = (0 until (r?.length() ?: 0)).map { r!!.optString(it) }.filter { it.isNotBlank() },
                sommeil = o.optInt("sommeil", 0),
                vitesse = o.optDouble("vitesse", 1.0),
                dernier = o.optString("dernier"),
            )
        }
    }
}

/**
 * Les appels à la box. Tout passe par l'API publique de l'AudioBox, sur ton réseau :
 * aucun compte, aucun service extérieur.
 */
class AudioBoxApi(private val adresse: String) {

    private val base = adresse.trimEnd('/')

    private suspend fun appel(methode: String, chemin: String, corps: JSONObject? = null): String =
        withContext(Dispatchers.IO) {
            val c = URL(base + chemin).openConnection() as HttpURLConnection
            try {
                c.requestMethod = methode
                c.connectTimeout = 4000
                c.readTimeout = 8000
                if (corps != null) {
                    c.doOutput = true
                    c.setRequestProperty("Content-Type", "application/json")
                    c.outputStream.use { it.write(corps.toString().toByteArray()) }
                }
                val code = c.responseCode
                val texte = (if (code < 400) c.inputStream else c.errorStream)
                    ?.bufferedReader()?.use { it.readText() } ?: ""
                if (code >= 400) throw IOException("La box a répondu $code")
                texte
            } finally {
                c.disconnect()
            }
        }

    suspend fun etat(): Etat = Etat.lire(JSONObject(appel("GET", "/api/public/state")))

    suspend fun lecture() { appel("POST", "/api/public/play") }
    suspend fun pause() { appel("POST", "/api/public/pause") }
    suspend fun stop() { appel("POST", "/api/public/stop") }
    suspend fun volume(niveau: Int) { appel("POST", "/api/public/volume/${niveau.coerceIn(0, 100)}") }
    suspend fun allerA(secondes: Double) { appel("POST", "/api/public/seek/${secondes.coerceAtLeast(0.0)}") }
    suspend fun reculer() { appel("POST", "/api/public/precedent") }
    suspend fun avancer() { appel("POST", "/api/public/suivant") }

    suspend fun radio(nom: String) {
        appel("POST", "/api/public/radio/" + URLEncoder.encode(nom, "UTF-8").replace("+", "%20"))
    }

    suspend fun minuterie(minutes: Int) {
        appel("POST", "/api/player/sleep", JSONObject().put("minutes", minutes))
    }

    suspend fun vitesse(v: Double) {
        appel("POST", "/api/player/speed", JSONObject().put("speed", v))
    }

    /** La pochette : une adresse de la box (« /api/abs/cover/… ») ou une adresse web. */
    suspend fun pochette(image: String): Bitmap? = withContext(Dispatchers.IO) {
        if (image.isBlank()) return@withContext null
        val url = if (image.startsWith("/")) base + image else image
        try {
            val c = URL(url).openConnection() as HttpURLConnection
            c.connectTimeout = 4000
            c.readTimeout = 8000
            try {
                if (c.responseCode >= 400) null
                else c.inputStream.use { BitmapFactory.decodeStream(it) }
            } finally {
                c.disconnect()
            }
        } catch (e: Exception) {
            null
        }
    }
}
