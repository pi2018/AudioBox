"""Ajout de la box depuis Paramètres › Appareils et services › Ajouter une intégration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AudioBoxApi, AudioBoxErreur
from .const import CONF_TOKEN, DEFAUT_HOTE, DEFAUT_PORT, DOMAIN


class AudioBoxConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        erreurs: dict[str, str] = {}
        if user_input is not None:
            api = AudioBoxApi(async_get_clientsession(self.hass), user_input[CONF_HOST],
                              user_input[CONF_PORT], user_input.get(CONF_TOKEN, ""))
            try:
                await api.etat()
            except AudioBoxErreur:
                erreurs["base"] = "injoignable"
            else:
                try:
                    if user_input.get(CONF_TOKEN):
                        await api.verifier_code()
                except AudioBoxErreur:
                    erreurs[CONF_TOKEN] = "code_refuse"
            if not erreurs:
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="AudioBox", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=DEFAUT_HOTE): str,
            vol.Required(CONF_PORT, default=DEFAUT_PORT): int,
            vol.Optional(CONF_TOKEN, default=""): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=erreurs)
