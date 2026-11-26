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
    /** Le livre en cours (pour ses chapitres). */
    val livreId: String = "",
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
                livreId = if (o.isNull("item_id")) "" else o.optString("item_id"),
            )
        }
    }
}

data class Livre(
    val id: String, val titre: String, val auteur: String,
    val duree: Double, val progression: Double, val termine: Boolean,
)

data class Chapitre(val titre: String, val debut: Double)

data class RadioTrouvee(val nom: String, val url: String, val logo: String, val pays: String)

data class Bibliotheque(val livres: List<Livre>, val enCours: List<Livre>, val configure: Boolean)

/**
 * Les appels à la box. Tout passe par l'API publique de l'AudioBox, sur ton réseau :
 * aucun compte, aucun service extérieur.
 */
class AudioBoxApi(private val adresse: String) {

    private val base = adresse.trimEnd('/')

    /** Le message de la box (« detail »), sinon un texte simple. */
    private fun messageDErreur(code: Int, texte: String): String {
        val detail = try { JSONObject(texte).optString("detail") } catch (e: Exception) { "" }
        if (detail.isNotBlank()) return detail
        return "La box a répondu $code"
    }

    private suspend fun appel(methode: String, chemin: String, corps: JSONObject? = null): String =
        withContext(Dispatchers.IO) {
            val c = URL(base + chemin).openConnection() as HttpURLConnection
            try {
                c.requestMethod = methode
                c.connectTimeout = 4000
                c.readTimeout = 20000
                if (corps != null) {
                    c.doOutput = true
                    c.setRequestProperty("Content-Type", "application/json")
                    c.outputStream.use { it.write(corps.toString().toByteArray()) }
                }
                val reponse = c.responseCode
                val texte = (if (reponse < 400) c.inputStream else c.errorStream)
                    ?.bufferedReader()?.use { it.readText() } ?: ""
                if (reponse >= 400) throw IOException(messageDErreur(reponse, texte))
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

    private fun livre(o: JSONObject) = Livre(
        o.optString("id"), o.optString("titre"), o.optString("auteur"),
        o.optDouble("duree", 0.0), o.optDouble("progression", 0.0), o.optBoolean("termine"),
    )

    private fun livres(a: org.json.JSONArray?): List<Livre> =
        (0 until (a?.length() ?: 0)).map { livre(a!!.getJSONObject(it)) }

    suspend fun bibliotheque(recherche: String = "", rafraichir: Boolean = false): Bibliotheque {
        val o = JSONObject(appel("GET",
            "/api/public/livres?q=" + URLEncoder.encode(recherche, "UTF-8") + (if (rafraichir) "&rafraichir=true" else "")))
        return Bibliotheque(livres(o.optJSONArray("livres")), livres(o.optJSONArray("en_cours")), o.optBoolean("configure", true))
    }

    suspend fun lancerLivre(id: String) { appel("POST", "/api/public/livre/" + URLEncoder.encode(id, "UTF-8")) }

    suspend fun chapitres(id: String): List<Chapitre> {
        val a = JSONObject(appel("GET", "/api/public/livre/" + URLEncoder.encode(id, "UTF-8") + "/chapitres")).optJSONArray("chapitres")
        return (0 until (a?.length() ?: 0)).map {
            val c = a!!.getJSONObject(it)
            Chapitre(c.optString("title").ifBlank { "Chapitre ${it + 1}" }, c.optDouble("start", 0.0))
        }
    }

    suspend fun chercherRadios(recherche: String): List<RadioTrouvee> {
        val a = JSONObject(appel("GET", "/api/public/radios/recherche?q=" + URLEncoder.encode(recherche, "UTF-8"))).optJSONArray("radios")
        return (0 until (a?.length() ?: 0)).map {
            val r = a!!.getJSONObject(it)
            RadioTrouvee(r.optString("name"), r.optString("url"), r.optString("favicon"), r.optString("pays"))
        }
    }

    suspend fun ajouterRadio(nom: String, url: String, logo: String = "") {
        appel("POST", "/api/public/radios",
            JSONObject().put("name", nom).put("url", url).put("favicon", logo))
    }

    suspend fun supprimerRadio(nom: String) {
        appel("DELETE", "/api/public/radios/" + URLEncoder.encode(nom, "UTF-8").replace("+", "%20"))
    }

    /** La pochette : une adresse de la box (« /api/abs/cover/… ») ou une adresse web. */
    suspend fun pochette(image: String): Bitmap? = withContext(Dispatchers.IO) {
        if (image.isBlank()) return@withContext null
        val cle = base + image
        synchronized(CACHE) { CACHE[cle] }?.let { return@withContext it }
        val url = if (image.startsWith("/")) base + image else image
        try {
            val c = URL(url).openConnection() as HttpURLConnection
            c.connectTimeout = 4000
            c.readTimeout = 8000
            try {
                if (c.responseCode >= 400) null
                else c.inputStream.use { BitmapFactory.decodeStream(it) }
                    ?.also { b -> synchronized(CACHE) { CACHE[cle] = b } }
            } finally {
                c.disconnect()
            }
        } catch (e: Exception) {
            null
        }
    }

    private companion object {
        /** Les 60 dernières pochettes vues : la liste des livres ne les redemande pas. */
        val CACHE = object : LinkedHashMap<String, Bitmap>(64, 0.75f, true) {
            override fun removeEldestEntry(e: MutableMap.MutableEntry<String, Bitmap>?) = size > 60
        }
    }
}
