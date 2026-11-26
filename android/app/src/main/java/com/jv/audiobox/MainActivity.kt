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
import androidx.compose.foundation.layout.heightIn
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

private enum class Onglet(val nom: String) { LECTURE("Lecture"), LIVRES("Livres"), RADIOS("Radios"), REGLAGES("Réglages") }

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
                Onglet.LIVRES -> EcranLivres(theme, box) { onglet = Onglet.LECTURE; portee.launch { try { etat = box.etat() } catch (e: Exception) {} } }
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
                    fontSize = 14.sp,
                    modifier = Modifier
                        .background(if (choisi) theme.doux else Color.Transparent, RoundedCornerShape(14.dp))
                        .clickable { onglet = o }
                        .padding(horizontal = 12.dp, vertical = 12.dp),
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
            Text("Choisis un livre dans l'onglet Livres\nou une radio dans l'onglet Radios.",
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

        if (etat.estUnLivre && etat.livreId.isNotBlank()) {
            var chapitres by remember(etat.livreId) { mutableStateOf<List<Chapitre>>(emptyList()) }
            var ouverts by remember(etat.livreId) { mutableStateOf(false) }
            LaunchedEffect(etat.livreId) { chapitres = try { box.chapitres(etat.livreId) } catch (e: Exception) { emptyList() } }
            if (chapitres.isNotEmpty()) {
                val actuel = chapitres.indexOfLast { it.debut <= etat.position + 0.5 }.coerceAtLeast(0)
                Spacer(Modifier.height(14.dp))
                Pastille(if (ouverts) "Masquer les chapitres" else "Chapitres (${actuel + 1}/${chapitres.size})", ouverts, theme) { ouverts = !ouverts }
                if (ouverts) {
                    Spacer(Modifier.height(8.dp))
                    Column(
                        Modifier.fillMaxWidth().heightIn(max = 280.dp)
                            .background(Couleurs.carte, RoundedCornerShape(14.dp)).verticalScroll(rememberScrollState()),
                    ) {
                        chapitres.forEachIndexed { i, c ->
                            Row(
                                Modifier.fillMaxWidth().clickable { agir { box.allerA(c.debut) } }.padding(horizontal = 14.dp, vertical = 11.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(c.titre, color = if (i == actuel) theme.accent else Couleurs.texte, fontSize = 14.sp,
                                    fontWeight = if (i == actuel) FontWeight.Bold else FontWeight.Normal,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                                Text(temps(c.debut), color = Couleurs.doux, fontSize = 12.sp)
                            }
                        }
                    }
                }
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
private fun Champ(valeur: String, surChange: (String) -> Unit, libelle: String, theme: Theme, modifier: Modifier = Modifier) {
    OutlinedTextField(
        value = valeur, onValueChange = surChange, singleLine = true,
        label = { Text(libelle, color = Couleurs.doux) },
        colors = OutlinedTextFieldDefaults.colors(
            focusedTextColor = Couleurs.texte, unfocusedTextColor = Couleurs.texte,
            focusedBorderColor = theme.accent, unfocusedBorderColor = Couleurs.trait,
            cursorColor = theme.accent,
        ),
        modifier = modifier.fillMaxWidth(),
    )
}

@Composable
private fun LigneLivre(livre: Livre, theme: Theme, box: AudioBoxApi, enCours: Boolean, surClic: () -> Unit) {
    var image by remember(livre.id) { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(livre.id) { image = box.pochette("/api/abs/cover/" + livre.id) }
    Row(
        Modifier.fillMaxWidth().background(Couleurs.carte, RoundedCornerShape(14.dp))
            .clickable(onClick = surClic).padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(62.dp).background(theme.pochette, RoundedCornerShape(10.dp)), contentAlignment = Alignment.Center) {
            val img = image
            if (img != null) Image(img.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            else Text("📚", fontSize = 22.sp)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(livre.titre, color = Couleurs.texte, fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (livre.auteur.isNotBlank()) Text(livre.auteur, color = Couleurs.doux, fontSize = 13.sp,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            val sous = when {
                livre.termine -> "Terminé"
                livre.progression > 0.005 -> "${(livre.progression * 100).toInt()} % · reste " + temps(livre.duree * (1 - livre.progression))
                livre.duree > 0 -> temps(livre.duree)
                else -> ""
            }
            if (sous.isNotEmpty()) Text(sous, color = if (enCours) theme.accent else Couleurs.doux, fontSize = 12.sp)
            if (livre.progression > 0.005 && !livre.termine) {
                Spacer(Modifier.height(5.dp))
                Box(Modifier.fillMaxWidth().height(4.dp).background(Couleurs.trait, RoundedCornerShape(2.dp))) {
                    Box(Modifier.fillMaxWidth(livre.progression.toFloat().coerceIn(0f, 1f)).height(4.dp)
                        .background(theme.accent, RoundedCornerShape(2.dp)))
                }
            }
        }
    }
}

@Composable
private fun EcranLivres(theme: Theme, box: AudioBoxApi, surLance: () -> Unit) {
    var recherche by remember { mutableStateOf("") }
    var biblio by remember { mutableStateOf<Bibliotheque?>(null) }
    var message by remember { mutableStateOf("") }
    var charge by remember { mutableStateOf(true) }
    var relire by remember { mutableStateOf(0) }
    var lance by remember { mutableStateOf("") }
    val portee = rememberCoroutineScope()

    LaunchedEffect(box, recherche, relire) {
        if (recherche.isNotEmpty()) delay(350)
        charge = true
        try {
            biblio = box.bibliotheque(recherche, rafraichir = relire > 0 && recherche.isEmpty())
            message = ""
        } catch (e: Exception) {
            message = e.message ?: "La bibliothèque ne répond pas"
        }
        charge = false
    }

    val ouvrir: (Livre) -> Unit = { livre ->
        if (lance.isEmpty()) {
            lance = livre.id
            portee.launch {
                try {
                    box.lancerLivre(livre.id)
                    message = ""
                    surLance()
                } catch (e: Exception) {
                    message = e.message ?: "Le livre ne démarre pas"
                }
                lance = ""
            }
        }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Spacer(Modifier.height(12.dp))
        Champ(recherche, { recherche = it }, "Chercher un titre ou un auteur", theme)
        Spacer(Modifier.height(6.dp))
        if (message.isNotEmpty()) Text(message, color = Color(0xFFFFB4A8), fontSize = 13.sp, modifier = Modifier.padding(vertical = 6.dp))
        if (lance.isNotEmpty()) Text("Lancement du livre…", color = theme.accent, fontSize = 13.sp, modifier = Modifier.padding(vertical = 6.dp))
        val b = biblio
        if (b == null) {
            if (charge) Text("Chargement des livres…", color = Couleurs.doux, fontSize = 14.sp, modifier = Modifier.padding(8.dp))
        } else if (!b.configure) {
            Text("Audiobookshelf n'est pas réglé sur la box (Paramètres › Audiobookshelf).", color = Couleurs.doux, fontSize = 14.sp,
                modifier = Modifier.padding(8.dp))
        } else {
            LazyColumn(Modifier.weight(1f).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (b.enCours.isNotEmpty()) {
                    item(key = "t-cours") { Text("Continuer l'écoute", color = theme.accent, fontSize = 13.sp, fontWeight = FontWeight.Bold) }
                    items(b.enCours, key = { "c-" + it.id }) { l -> LigneLivre(l, theme, box, true) { ouvrir(l) } }
                }
                item(key = "t-tous") {
                    Row(Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(if (recherche.isEmpty()) "Tous les livres (${b.livres.size})" else "${b.livres.size} résultat(s)",
                            color = theme.accent, fontSize = 13.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        if (recherche.isEmpty()) Pastille("Actualiser", false, theme) { relire++ }
                    }
                }
                if (b.livres.isEmpty()) item(key = "vide") {
                    Text(if (recherche.isEmpty()) "Aucun livre trouvé." else "Aucun résultat.", color = Couleurs.doux, fontSize = 14.sp)
                }
                items(b.livres, key = { "l-" + it.id }) { l -> LigneLivre(l, theme, box, false) { ouvrir(l) } }
                item(key = "bas") { Spacer(Modifier.height(10.dp)) }
            }
        }
    }
}

@Composable
private fun EcranRadios(etat: Etat?, theme: Theme, agir: (suspend () -> Unit) -> Unit, box: AudioBoxApi) {
    val radios = etat?.radios ?: emptyList()
    var aRetirer by remember { mutableStateOf("") }
    var recherche by remember { mutableStateOf("") }
    var trouvees by remember { mutableStateOf<List<RadioTrouvee>>(emptyList()) }
    var info by remember { mutableStateOf("") }
    var main by remember { mutableStateOf(false) }
    var nomMain by remember { mutableStateOf("") }
    var urlMain by remember { mutableStateOf("") }
    val portee = rememberCoroutineScope()

    LazyColumn(
        Modifier.fillMaxSize().padding(horizontal = 18.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item { Spacer(Modifier.height(6.dp)) }
        if (radios.isEmpty()) item {
            Text("Aucune radio pour l'instant : ajoutes-en une en bas.", color = Couleurs.doux, fontSize = 14.sp)
        }
        items(radios, key = { "r-" + it }) { nom ->
            val enCours = etat?.origine == "radio" && etat.titre == nom && !etat.arrete
            Row(
                Modifier
                    .fillMaxWidth()
                    .background(Couleurs.carte, RoundedCornerShape(16.dp))
                    .border(2.dp, if (enCours) theme.accent else Color.Transparent, RoundedCornerShape(16.dp)),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(Modifier.weight(1f).clickable { agir { box.radio(nom) } }.padding(horizontal = 18.dp, vertical = 18.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(nom, color = Couleurs.texte, fontSize = 18.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.weight(1f))
                    if (enCours) Text("En écoute", color = theme.accent, fontSize = 13.sp)
                }
                Text(
                    if (aRetirer == nom) "Retirer ?" else "✕",
                    color = if (aRetirer == nom) Color(0xFFFFB4A8) else Couleurs.doux, fontSize = 15.sp,
                    modifier = Modifier.clickable {
                        if (aRetirer == nom) { aRetirer = ""; agir { box.supprimerRadio(nom) } } else aRetirer = nom
                    }.padding(horizontal = 16.dp, vertical = 18.dp),
                )
            }
        }

        item {
            Spacer(Modifier.height(10.dp))
            Text("Ajouter une radio", color = Couleurs.texte, fontSize = 17.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            Champ(recherche, { recherche = it }, "Nom de la radio (ex. France Inter)", theme)
            Spacer(Modifier.height(8.dp))
            Pastille("Chercher", true, theme) {
                portee.launch {
                    try {
                        trouvees = box.chercherRadios(recherche)
                        info = if (trouvees.isEmpty()) "Aucune radio trouvée." else ""
                    } catch (e: Exception) {
                        info = e.message ?: "Recherche impossible"
                    }
                }
            }
            if (info.isNotEmpty()) Text(info, color = Couleurs.doux, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
        }
        items(trouvees, key = { "t-" + it.url }) { r ->
            val deja = radios.any { it.equals(r.nom, ignoreCase = true) }
            Row(
                Modifier.fillMaxWidth().background(Couleurs.carte, RoundedCornerShape(14.dp)).padding(horizontal = 14.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(r.nom, color = Couleurs.texte, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (r.pays.isNotBlank()) Text(r.pays, color = Couleurs.doux, fontSize = 12.sp)
                }
                if (deja) Text("Ajoutée", color = Couleurs.doux, fontSize = 13.sp)
                else Pastille("Ajouter", false, theme) { agir { box.ajouterRadio(r.nom, r.url, r.logo) } }
            }
        }
        item {
            Spacer(Modifier.height(4.dp))
            Text(if (main) "Masquer l'adresse à la main" else "Ou avec l'adresse du flux…", color = theme.accent, fontSize = 14.sp,
                modifier = Modifier.clickable { main = !main }.padding(vertical = 6.dp))
            if (main) {
                Champ(nomMain, { nomMain = it }, "Nom", theme)
                Spacer(Modifier.height(8.dp))
                Champ(urlMain, { urlMain = it }, "Adresse du flux (http://…)", theme)
                Spacer(Modifier.height(8.dp))
                Pastille("Ajouter cette radio", true, theme) {
                    agir { box.ajouterRadio(nomMain, urlMain); nomMain = ""; urlMain = "" }
                }
            }
            Spacer(Modifier.height(16.dp))
        }
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
