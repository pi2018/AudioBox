"""
Essai de bout en bout de l'intégration Home Assistant, contre un vrai serveur
AudioBox lancé sur ce poste (variable AUDIOBOX_URL, ex. http://127.0.0.1:8123x).

    AUDIOBOX_PORT=8777 python3 -m pytest tests_ha -q
"""
import os

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.audiobox.const import CONF_TOKEN, DOMAIN

PORT = int(os.environ.get("AUDIOBOX_PORT", "8777"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_lecteur_cree_et_pilote(hass: HomeAssistant, socket_enabled) -> None:
    assert await async_setup_component(hass, "media_source", {})
    entree = MockConfigEntry(domain=DOMAIN, unique_id=f"127.0.0.1:{PORT}",
                             data={CONF_HOST: "127.0.0.1", CONF_PORT: PORT, CONF_TOKEN: ""})
    entree.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entree.entry_id)
    await hass.async_block_till_done()

    etat = hass.states.get("media_player.audiobox")
    assert etat is not None, [s.entity_id for s in hass.states.async_all()]
    assert etat.state == "idle"
    assert etat.attributes["volume_level"] == 0.8
    assert etat.attributes["source_list"] == ["France Inter", "FIP"]

    await hass.services.async_call("media_player", "volume_set",
                                   {"entity_id": "media_player.audiobox", "volume_level": 0.42},
                                   blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("media_player.audiobox").attributes["volume_level"] == 0.42
