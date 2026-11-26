package com.jv.audiobox

import android.content.Context
import androidx.compose.ui.graphics.Color

/** L'adresse de la box et la couleur choisie, gardées sur le téléphone. */
object Reglages {
    private const val FICHIER = "audiobox"
    const val ADRESSE_DEFAUT = "http://192.168.178.77:8000"

    fun adresse(c: Context): String =
        c.getSharedPreferences(FICHIER, Context.MODE_PRIVATE).getString("adresse", ADRESSE_DEFAUT) ?: ADRESSE_DEFAUT

    fun ecrireAdresse(c: Context, adresse: String) {
        c.getSharedPreferences(FICHIER, Context.MODE_PRIVATE).edit().putString("adresse", normaliser(adresse)).apply()
    }

    /**
     * « 192.168.178.77 » → « http://192.168.178.77:8000 ». Sans « http:// », l'appli ne
     * joignait pas la box ; « http://http://… » et la barre finale sont aussi enlevés.
     */
    fun normaliser(adresse: String): String {
        var a = adresse.trim()
        var schema = "http"
        while (true) {
            val bas = a.lowercase()
            if (bas.startsWith("http://")) {
                schema = "http"; a = a.substring(7)
            } else if (bas.startsWith("https://")) {
                schema = "https"; a = a.substring(8)
            } else {
                break
            }
        }
        a = a.trim('/')
        if (a.isEmpty()) return ADRESSE_DEFAUT
        // La box répond sur le port 8000 (une adresse https passe par un relais : on n'y touche pas).
        if (schema == "http" && !a.contains(':') && !a.contains('/')) a += ":8000"
        return "$schema://$a"
    }

    fun theme(c: Context): String =
        c.getSharedPreferences(FICHIER, Context.MODE_PRIVATE).getString("theme", "violet") ?: "violet"

    fun ecrireTheme(c: Context, id: String) {
        c.getSharedPreferences(FICHIER, Context.MODE_PRIVATE).edit().putString("theme", id).apply()
    }
}

/** Les mêmes 6 couleurs que l'écran de la box. */
data class Theme(val id: String, val nom: String, val accent: Color, val encre: Color, val doux: Color, val pochette: Color)

val THEMES = listOf(
    Theme("violet", "Violet", Color(0xFFA99BFF), Color(0xFF14111F), Color(0xFF262236), Color(0xFF2B2546)),
    Theme("menthe", "Menthe", Color(0xFF7FD1B9), Color(0xFF0F1D19), Color(0xFF1C2E2A), Color(0xFF21403A)),
    Theme("ambre", "Ambre", Color(0xFFF2A65A), Color(0xFF1F1408), Color(0xFF33261A), Color(0xFF4A341F)),
    Theme("corail", "Corail", Color(0xFFFF8A7A), Color(0xFF24110E), Color(0xFF36211F), Color(0xFF4C2A26)),
    Theme("bleu", "Bleu", Color(0xFF6EA8FF), Color(0xFF0C1626), Color(0xFF1B2638), Color(0xFF1F3352)),
    Theme("rose", "Rose", Color(0xFFF48FC6), Color(0xFF24101B), Color(0xFF33202C), Color(0xFF4A2740)),
)

object Couleurs {
    val fond = Color(0xFF0E0F13)
    val barre = Color(0xFF15171D)
    val carte = Color(0xFF1C1E26)
    val trait = Color(0xFF2A2C36)
    val texte = Color(0xFFECECF1)
    val doux = Color(0xFFA3A4B2)
}
