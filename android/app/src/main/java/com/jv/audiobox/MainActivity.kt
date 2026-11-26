package com.jv.audiobox

import android.graphics.Bitmap
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { Appli() }
    }
}

private enum class Onglet(val nom: String) { LECTURE("Lecture"), RADIOS("Radios"), REGLAGES("Réglages") }

@Composable
private fun Appli() {
    val contexte = LocalContext.current
    var adresse by remember { mutableStateOf(Reglages.adresse(contexte)) }
    var themeId by remember { mutableStateOf(Reglages.theme(contexte)) }
    val theme = THEMES.firstOrNull { it.id == themeId } ?: THEMES[0]
    val box = remember(adresse) { AudioBoxApi(adresse) }

    var etat by remember { mutableStateOf<Etat?>(null) }
    var erreur by remember { mutableStateOf("") }
    var onglet by remember { mutableStateOf(Onglet.LECTURE) }
    val portee = rememberCoroutineScope()

    // L'état de la box toutes les 2 secondes, seulement quand l'appli est à l'écran.
    val cycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(box) {
        cycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                try {
                    etat = box.etat()
                    erreur = ""
                } catch (e: Exception) {
                    erreur = "La box ne répond pas à $adresse"
                }
                delay(2000)
            }
        }
    }

    // Lance une commande, puis relit l'état tout de suite.
    val agir: (suspend () -> Unit) -> Unit = { action ->
        portee.launch {
            try {
                action()
                etat = box.etat()
                erreur = ""
            } catch (e: Exception) {
                erreur = "Commande non reçue : ${e.message ?: "erreur"}"
            }
        }
    }

    Column(Modifier.fillMaxSize().background(Couleurs.fond).systemBarsPadding()) {
        if (erreur.isNotEmpty()) {
            Text(
                erreur, color = Color(0xFFFFB4A8), fontSize = 13.sp,
                modifier = Modifier.fillMaxWidth().background(Color(0xFF3A1E1E)).padding(12.dp),
            )
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when (onglet) {
                Onglet.LECTURE -> EcranLecture(etat, theme, box, agir)
                Onglet.RADIOS -> EcranRadios(etat, theme, agir, box)
                Onglet.REGLAGES -> EcranReglages(
                    adresse, theme,
                    surAdresse = { nouvelle -> Reglages.ecrireAdresse(contexte, nouvelle); adresse = Reglages.normaliser(nouvelle) },
                    surTheme = { id -> Reglages.ecrireTheme(contexte, id); themeId = id },
                )
            }
        }
        Row(
            Modifier.fillMaxWidth().background(Couleurs.barre).padding(horizontal = 8.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            Onglet.entries.forEach { o ->
                val choisi = o == onglet
                Text(
                    o.nom,
                    color = if (choisi) theme.accent else Couleurs.doux,
                    fontWeight = if (choisi) FontWeight.Bold else FontWeight.Normal,
                    fontSize = 15.sp,
                    modifier = Modifier
                        .background(if (choisi) theme.doux else Color.Transparent, RoundedCornerShape(14.dp))
                        .clickable { onglet = o }
                        .padding(horizontal = 18.dp, vertical = 12.dp),
                )
            }
        }
    }
}

private fun temps(s: Double): String {
    val t = s.toLong().coerceAtLeast(0)
    val h = t / 3600
    val m = (t % 3600) / 60
    val sec = t % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, sec) else "%d:%02d".format(m, sec)
}

@Composable
private fun Rond(texte: String, taille: Int, fond: Color, encre: Color, surClic: () -> Unit) {
    Box(
        Modifier.size(taille.dp).background(fond, CircleShape).clickable(onClick = surClic),
        contentAlignment = Alignment.Center,
    ) {
        Text(texte, color = encre, fontSize = (taille / 3.2).sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun Pastille(texte: String, choisie: Boolean, theme: Theme, surClic: () -> Unit) {
    Text(
        texte,
        color = if (choisie) theme.encre else Couleurs.texte,
        fontSize = 13.sp,
        fontWeight = FontWeight.Medium,
        modifier = Modifier
            .background(if (choisie) theme.accent else Couleurs.carte, RoundedCornerShape(20.dp))
            .clickable(onClick = surClic)
            .padding(horizontal = 14.dp, vertical = 9.dp),
    )
}

@Composable
private fun EcranLecture(etat: Etat?, theme: Theme, box: AudioBoxApi, agir: (suspend () -> Unit) -> Unit) {
    if (etat == null || etat.arrete) {
        Column(
            Modifier.fillMaxSize().padding(28.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Rien ne joue", color = Couleurs.texte, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Text("Choisis une radio dans l'onglet Radios,\nou lance un livre sur l'écran de la box.",
                color = Couleurs.doux, fontSize = 14.sp)
            // La dernière écoute peut repartir d'ici (un livre reprend là où il s'était arrêté).
            val dernier = etat?.dernier ?: ""
            if (dernier.isNotBlank()) {
                Spacer(Modifier.height(26.dp))
                Rond("▶", 80, theme.accent, theme.encre) { agir { box.lecture() } }
                Spacer(Modifier.height(10.dp))
                Text("Reprendre : $dernier", color = Couleurs.texte, fontSize = 15.sp,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
        return
    }

    var image by remember { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(etat.image) { image = box.pochette(etat.image) }

    // Pendant qu'on fait glisser la barre, on garde la valeur du doigt.
    var glisse: Float? by remember { mutableStateOf<Float?>(null) }
    var volumeGlisse: Float? by remember { mutableStateOf<Float?>(null) }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier.size(260.dp).background(theme.pochette, RoundedCornerShape(18.dp)),
            contentAlignment = Alignment.BottomStart,
        ) {
            val img = image
            if (img != null) {
                Image(img.asImageBitmap(), contentDescription = "Pochette",
                    contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            } else {
                Text(etat.titre.ifBlank { "AudioBox" }, color = Color.White, fontSize = 24.sp,
                    fontWeight = FontWeight.Bold, modifier = Modifier.padding(18.dp),
                    maxLines = 3, overflow = TextOverflow.Ellipsis)
            }
        }
        Spacer(Modifier.height(18.dp))
        Text(
            when (etat.origine) { "abs" -> "LIVRE AUDIO"; "radio" -> "RADIO"; "podcast" -> "PODCAST"; else -> "EN ÉCOUTE" },
            color = theme.accent, fontSize = 12.sp, fontWeight = FontWeight.Bold,
        )
        Text(etat.titre.ifBlank { "Sans titre" }, color = Couleurs.texte, fontSize = 22.sp,
            fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis)
        if (etat.auteur.isNotBlank()) Text(etat.auteur, color = Couleurs.doux, fontSize = 15.sp)

        if (etat.duree > 0) {
            Spacer(Modifier.height(12.dp))
            val fraction = (etat.position / etat.duree).toFloat().coerceIn(0f, 1f)
            Slider(
                value = glisse ?: fraction,
                onValueChange = { glisse = it },
                onValueChangeFinished = {
                    val cible = (glisse ?: fraction) * etat.duree
                    glisse = null
                    agir { box.allerA(cible) }
                },
                colors = SliderDefaults.colors(thumbColor = theme.accent, activeTrackColor = theme.accent,
                    inactiveTrackColor = Couleurs.trait),
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(temps(etat.position), color = Couleurs.doux, fontSize = 12.sp)
                Text("reste " + temps(etat.duree - etat.position), color = Couleurs.doux, fontSize = 12.sp)
            }
        }

        Spacer(Modifier.height(14.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            if (etat.duree > 0) Rond("−30", 56, Couleurs.carte, Couleurs.texte) { agir { box.reculer() } }
            Rond(if (etat.joue) "❚❚" else "▶", 80, theme.accent, theme.encre) {
                agir { if (etat.joue) box.pause() else box.lecture() }
            }
            if (etat.duree > 0) Rond("+30", 56, Couleurs.carte, Couleurs.texte) { agir { box.avancer() } }
            Rond("■", 56, Couleurs.carte, Couleurs.texte) { agir { box.stop() } }
        }

        Spacer(Modifier.height(18.dp))
        val vg: Float? = volumeGlisse
        val volumeAffiche = if (vg != null) (vg * 100).toInt() else etat.volume
        Text("Volume $volumeAffiche %", color = Couleurs.doux, fontSize = 13.sp)
        Slider(
            value = volumeGlisse ?: (etat.volume / 100f),
            onValueChange = { volumeGlisse = it },
            onValueChangeFinished = {
                // Sans valeur du doigt, on garde le volume actuel (avant : 0, le son coupait).
                val v = ((volumeGlisse ?: (etat.volume / 100f)) * 100).toInt()
                volumeGlisse = null
                agir { box.volume(v) }
            },
            colors = SliderDefaults.colors(thumbColor = theme.accent, activeTrackColor = theme.accent,
                inactiveTrackColor = Couleurs.trait),
        )

        Spacer(Modifier.height(10.dp))
        Text(
            if (etat.sommeil > 0) "Sommeil : arrêt dans ${temps(etat.sommeil.toDouble())}" else "Minuterie de sommeil",
            color = Couleurs.doux, fontSize = 13.sp,
        )
        Spacer(Modifier.height(6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pastille("Non", etat.sommeil == 0, theme) { agir { box.minuterie(0) } }
            listOf(15, 30, 60).forEach { m ->
                Pastille("$m min", false, theme) { agir { box.minuterie(m) } }
            }
        }

        if (etat.estUnLivre) {
            Spacer(Modifier.height(14.dp))
            Text("Vitesse", color = Couleurs.doux, fontSize = 13.sp)
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(0.8, 1.0, 1.2, 1.5).forEach { v ->
                    val nom = if (v == 1.0) "1×" else "${v.toString().replace('.', ',')}×"
                    Pastille(nom, kotlin.math.abs(etat.vitesse - v) < 0.01, theme) { agir { box.vitesse(v) } }
                }
            }
        }
    }
}

@Composable
private fun EcranRadios(etat: Etat?, theme: Theme, agir: (suspend () -> Unit) -> Unit, box: AudioBoxApi) {
    val radios = etat?.radios ?: emptyList()
    if (radios.isEmpty()) {
        Column(Modifier.fillMaxSize().padding(28.dp), verticalArrangement = Arrangement.Center) {
            Text("Aucune radio", color = Couleurs.texte, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Text("Ajoute tes radios favorites dans Paramètres sur l'écran de la box.", color = Couleurs.doux, fontSize = 14.sp)
        }
        return
    }
    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item { Spacer(Modifier.height(12.dp)) }
        items(radios) { nom ->
            val enCours = etat?.origine == "radio" && etat.titre == nom && !etat.arrete
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(Couleurs.carte, RoundedCornerShape(16.dp))
                    .border(2.dp, if (enCours) theme.accent else Color.Transparent, RoundedCornerShape(16.dp))
                    .clickable { agir { box.radio(nom) } }
                    .padding(horizontal = 18.dp, vertical = 18.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(nom, color = Couleurs.texte, fontSize = 18.sp, fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f))
                if (enCours) Text("En écoute", color = theme.accent, fontSize = 13.sp)
            }
        }
        item { Spacer(Modifier.height(12.dp)) }
    }
}

@Composable
private fun EcranReglages(adresse: String, theme: Theme, surAdresse: (String) -> Unit, surTheme: (String) -> Unit) {
    var saisie by remember(adresse) { mutableStateOf(adresse) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(22.dp)) {
        Text("Adresse de la box", color = Couleurs.texte, fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = saisie,
            onValueChange = { saisie = it },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
            colors = OutlinedTextFieldDefaults.colors(
                focusedTextColor = Couleurs.texte, unfocusedTextColor = Couleurs.texte,
                focusedBorderColor = theme.accent, unfocusedBorderColor = Couleurs.trait,
                cursorColor = theme.accent,
            ),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pastille("Enregistrer", true, theme) { surAdresse(saisie) }
            Pastille("Adresse d'origine", false, theme) { saisie = Reglages.ADRESSE_DEFAUT; surAdresse(saisie) }
        }
        Spacer(Modifier.height(8.dp))
        Text("Exemple : http://192.168.178.77:8000 (marche chez toi, sur ton Wi-Fi).",
            color = Couleurs.doux, fontSize = 13.sp)

        Spacer(Modifier.height(28.dp))
        Text("Couleur", color = Couleurs.texte, fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            THEMES.forEach { t ->
                Box(
                    Modifier
                        .size(44.dp)
                        .background(t.accent, CircleShape)
                        .border(3.dp, if (t.id == theme.id) Color.White else Color.Transparent, CircleShape)
                        .clickable { surTheme(t.id) },
                )
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(theme.nom, color = theme.accent, fontSize = 13.sp)
        Spacer(Modifier.width(1.dp))
    }
}
