"""L'AudioBox comme lecteur multimédia Home Assistant."""
from __future__ import annotations

from typing import Any

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    ATTR_MEDIA_ANNOUNCE,
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.components.media_player.browse_media import async_process_play_media_url
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import AudioBoxErreur
from .const import DOMAIN

FONCTIONS = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.SEEK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    donnees = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AudioBoxLecteur(donnees["coordinateur"], donnees["api"], entry)])


class AudioBoxLecteur(CoordinatorEntity, MediaPlayerEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = FONCTIONS
    _attr_media_image_remotely_accessible = False

    def __init__(self, coordinateur, api, entry: ConfigEntry) -> None:
        super().__init__(coordinateur)
        self._api = api
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name="AudioBox", manufacturer="JV", model="Raspberry Pi 4",
            configuration_url=api.base,
        )
        self._position_lue_a = None
        self._derniere_position = None

    @property
    def _etat(self) -> dict:
        return self.coordinator.data or {}

    @callback
    def _handle_coordinator_update(self) -> None:
        pos = self._etat.get("position")
        if pos != self._derniere_position:
            self._derniere_position = pos
            self._position_lue_a = dt_util.utcnow()
        super()._handle_coordinator_update()

    @property
    def state(self) -> MediaPlayerState:
        e = self._etat
        if e.get("playing"):
            return MediaPlayerState.PLAYING
        if e.get("paused"):
            return MediaPlayerState.PAUSED
        return MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        v = self._etat.get("volume")
        return None if v is None else v / 100

    @property
    def media_title(self) -> str | None:
        return self._etat.get("title") or None

    @property
    def media_artist(self) -> str | None:
        return self._etat.get("author") or None

    @property
    def media_content_type(self) -> str | None:
        source = self._etat.get("source")
        if source == "abs":
            return MediaType.PODCAST
        return MediaType.MUSIC if source else None

    @property
    def media_duration(self) -> int | None:
        d = self._etat.get("duration")
        return int(d) if d else None

    @property
    def media_position(self) -> int | None:
        p = self._etat.get("position")
        return int(p) if p is not None and not self._etat.get("stopped") else None

    @property
    def media_position_updated_at(self):
        return self._position_lue_a

    @property
    def media_image_url(self) -> str | None:
        image = self._etat.get("image") or ""
        if not image:
            return None
        return self._api.base + image if image.startswith("/") else image

    @property
    def source_list(self) -> list[str]:
        return self._etat.get("radios") or []

    @property
    def source(self) -> str | None:
        if self._etat.get("source") == "radio":
            return self._etat.get("title") or None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"minuterie_sommeil_s": self._etat.get("sommeil", 0),
                "vitesse": self._etat.get("vitesse", 1.0),
                "origine": self._etat.get("source", ""),
                # Ce que « lecture » relance quand tout est arrêté (dernière écoute).
                "derniere_ecoute": self._etat.get("dernier", "")}

    async def _faire(self, action) -> None:
        """Envoie l'ordre à la box, puis relit son état. Une erreur s'affiche dans HA."""
        try:
            await action
        except AudioBoxErreur as err:
            raise HomeAssistantError(f"AudioBox : {err}") from err
        # Relecture immédiate : la version « regroupée » attendait jusqu'à 10 s, et le
        # bouton lecture/pause de Home Assistant restait faux pendant ce temps.
        await self.coordinator.async_refresh()

    async def async_media_play(self) -> None:
        # Si tout est arrêté, la box relance la dernière écoute.
        await self._faire(self._api.lecture())

    async def async_media_pause(self) -> None:
        await self._faire(self._api.pause())

    async def async_media_stop(self) -> None:
        await self._faire(self._api.stop())

    async def async_set_volume_level(self, volume: float) -> None:
        await self._faire(self._api.volume(round(volume * 100)))

    async def async_volume_up(self) -> None:
        await self._faire(self._api.volume((self._etat.get("volume") or 0) + 5))

    async def async_volume_down(self) -> None:
        await self._faire(self._api.volume((self._etat.get("volume") or 0) - 5))

    async def async_media_seek(self, position: float) -> None:
        await self._faire(self._api.aller_a(position))

    async def async_media_next_track(self) -> None:
        await self._faire(self._api.suivant())

    async def async_media_previous_track(self) -> None:
        await self._faire(self._api.precedent())

    async def async_select_source(self, source: str) -> None:
        await self._faire(self._api.radio(source))

    async def async_browse_media(self, media_content_type: str | None = None,
                                 media_content_id: str | None = None) -> BrowseMedia:
        # Médias de Home Assistant (synthèse vocale, fichiers locaux, radio-browser…).
        return await media_source.async_browse_media(
            self.hass, media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        if media_source.is_media_source_id(media_id):
            lu = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
            media_id = lu.url
        # Une adresse relative de Home Assistant devient une adresse complète, joignable par la box.
        url = async_process_play_media_url(self.hass, media_id)
        if kwargs.get(ATTR_MEDIA_ANNOUNCE):
            await self._faire(self._api.annonce(url))
        else:
            await self._faire(self._api.lire_adresse(url))
