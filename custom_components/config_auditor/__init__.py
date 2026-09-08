"""H.A.C.A — Home Assistant Config Auditor v1.6.1"""
from __future__ import annotations

import asyncio

import logging
from contextlib import contextmanager, suppress
import shutil
from datetime import timedelta
from pathlib import Path
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as _dt_util
from .const import (
    MODULE_9_DASHBOARD_ANALYZER,
    MODULE_10_EVENT_MONITORING,
    MODULE_11_RECORDER_ANALYZER,
    MODULE_12_AUDIT_HISTORY,
    DOMAIN,
    NAME,
    VERSION,
    DEFAULT_SCAN_INTERVAL,
    MODULE_4_COMPLIANCE_REPORT,
    MODULE_5_REFACTORING_ASSISTANT,
    BACKUP_DIR,
    REPORTS_DIR,
    LEGACY_HISTORY_DIR,
    LEGACY_BATTERY_HISTORY_DIR,
    STORAGE_KEY_HISTORY,
    STORAGE_KEY_BATTERY_HISTORY,
    STORAGE_VERSION,
)
from .automation_analyzer import AutomationAnalyzer
from .entity_analyzer import EntityAnalyzer
from .battery_monitor import BatteryMonitor
from .dependency_mapper import DependencyMapper
from .performance_analyzer import PerformanceAnalyzer
from .security_analyzer import SecurityAnalyzer
from .dashboard_analyzer import DashboardAnalyzer
from .recorder_analyzer import RecorderAnalyzer
from .history_manager import HistoryManager
from .custom_panel import async_register_panel, async_unregister_panel, async_register_cards
from .websocket import async_register_websocket_handlers
from .conversation import async_setup_conversation
from .health_score import calculate_health_score
from .event_monitor import async_setup_event_monitor
from .repairs import async_update_repairs
from .services import async_setup_services
from .automation_optimizer import AutomationOptimizer

if MODULE_4_COMPLIANCE_REPORT:
    from .report_generator import ReportGenerator

if MODULE_5_REFACTORING_ASSISTANT:
    from .refactoring_assistant import RefactoringAssistant

# ── v1.4.0 ────────────────────────────────────────────────────────────────
from .const import (
    MODULE_15_MCP_SERVER,
    MODULE_16_PROACTIVE_AGENT,
    MODULE_17_COMPLIANCE_ANALYZER,
    OPT_MCP_SERVER_ENABLED,
    OPT_PROACTIVE_AGENT_ENABLED,
    OPT_LLM_API_ENABLED,
    DEFAULT_MCP_SERVER_ENABLED,
    DEFAULT_PROACTIVE_AGENT_ENABLED,
    DEFAULT_LLM_API_ENABLED,
)

if MODULE_15_MCP_SERVER:
    from .mcp_server import async_setup_mcp_server

from .llm_api import HacaLLMAPI, HACA_LLM_API_ID

if MODULE_16_PROACTIVE_AGENT:
    from .proactive_agent import async_setup_proactive_agent

if MODULE_17_COMPLIANCE_ANALYZER:
    from .compliance_analyzer import ComplianceAnalyzer

# ── v1.5.0 ────────────────────────────────────────────────────────────────
from .const import (
    MODULE_18_BATTERY_PREDICTOR,
    MODULE_19_AREA_COMPLEXITY,
    MODULE_20_REDUNDANCY_ANALYZER,
    MODULE_21_RECORDER_IMPACT,
)

if MODULE_18_BATTERY_PREDICTOR:
    from .battery_predictor import BatteryPredictor

if MODULE_19_AREA_COMPLEXITY:
    from .area_complexity_analyzer import AreaComplexityAnalyzer

if MODULE_20_REDUNDANCY_ANALYZER:
    from .redundancy_analyzer import RedundancyAnalyzer

if MODULE_21_RECORDER_IMPACT:
    from .recorder_impact_analyzer import RecorderImpactAnalyzer

from .const import MODULE_22_INTEGRATION_MONITOR
if MODULE_22_INTEGRATION_MONITOR:
    from .integration_analyzer import IntegrationAnalyzer


import json as _json
from pathlib import Path as _Path

# ── Cache mémoire des fichiers de traduction ────────────────────────────────
# Préchargé au démarrage via _async_preload_ts_cache() pour éviter tout I/O
# bloquant dans l'event loop (violation asyncio détectée par HA Python 3.14).
_TS_CACHE: dict[str, dict] = {}   # {lang: {section: {key: value}}}

# The same files, kept in their raw "panel" shape. The panel navigates from
# ``panel.*`` and would not find a key in the merged tree above, so the two
# forms are cached side by side rather than re-read from disk on every
# ``haca/get_translations`` — a ~130 KB JSON parse per panel open.
_TS_PANEL_CACHE: dict[str, dict] = {}   # {lang: raw "panel" subtree}


def _ts(hass, section: str, key: str, **kwargs) -> str:
    """Get a translation string from in-memory cache (never does file I/O).

    Notifications are server-side and must use a stable, system-wide locale.
    Resolution is delegated to ``translation_utils.resolve_notification_language``
    so the per-entry ``notification_language`` option (if set) takes precedence
    over the HA system language. The volatile per-panel ``user_language`` slot
    is never consulted here.
    """
    from .translation_utils import resolve_notification_language
    lang = resolve_notification_language(hass)
    data = _TS_CACHE.get(lang) or _TS_CACHE.get("en") or {}
    val = data.get(section, {}).get(key, key)
    try:
        return val.format(**kwargs) if kwargs else val
    except Exception:
        return val


async def _async_preload_ts_cache(hass: "HomeAssistant") -> None:
    """Pre-load all translation JSON files into _TS_CACHE using the thread pool."""
    trans_dir = _Path(__file__).parent / "translations"

    def _load_one(path: _Path) -> tuple[str, dict]:
        raw = _json.loads(path.read_text(encoding="utf-8"))
        # Merge strategy: start from the full root JSON, then overlay
        # the "panel" subtree on top.  This ensures both root-level
        # sections (ai_prompts, services_notif, notifications…) AND
        # panel-level sections (misc, buttons, tabs…) are accessible
        # via  cache.get(section, {}).get(key).
        # For sections that exist at BOTH levels (e.g. "notifications"),
        # keys from panel override root.
        panel = raw.get("panel", {})
        merged = {}
        for key, val in raw.items():
            if key == "panel":
                continue
            if isinstance(val, dict):
                merged[key] = dict(val)  # shallow copy
            else:
                merged[key] = val
        # Overlay panel sections on top
        for key, val in panel.items():
            if isinstance(val, dict):
                merged.setdefault(key, {}).update(val)
            else:
                merged[key] = val
        return path.stem, merged, panel

    def _list_translations() -> list[_Path]:
        """Blocking glob — must run in executor."""
        return sorted(trans_dir.glob("*.json"))

    import asyncio
    paths = await hass.async_add_executor_job(_list_translations)
    tasks = [hass.async_add_executor_job(_load_one, p) for p in paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if isinstance(res, tuple):
            lang_code, merged, raw_panel = res
            _TS_CACHE[lang_code] = merged
            _TS_PANEL_CACHE[lang_code] = raw_panel
    _LOGGER.debug("[HACA] Translation cache loaded: %s languages", len(_TS_CACHE))


_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

# Réglages de _wait_for_entities_to_settle() (détecteur de stabilisation au
# démarrage, utilisé par async_setup_entry) : combien de temps les états doivent
# cesser de bouger avant que le premier scan soit considéré comme fiable, à
# quelle fréquence on regarde, et le plancher en dessous duquel on ne déclare
# jamais « stabilisé ». Le plancher existe parce qu'un démarrage n'enregistre pas
# les entités de façon continue : un creux entre deux intégrations ressemble à
# une stabilisation, et sans lui une pause de quelques secondes juste après
# EVENT_HOMEASSISTANT_STARTED suffirait à lancer le scan avant que Zigbee/Z-Wave
# n'aient commencé à restaurer les leurs.
SETTLE_QUIET_SECONDS = 10
SETTLE_POLL_SECONDS = 2
SETTLE_MIN_SECONDS = 15


async def _wait_for_entities_to_settle(
    hass: HomeAssistant, ceiling_seconds: int
) -> None:
    """Attendre que la machine d'états cesse de bouger, au lieu de deviner.

    EVENT_HOMEASSISTANT_STARTED signifie seulement que le async_setup_entry()
    de chaque intégration a rendu la main : les intégrations lentes (Zigbee,
    Z-Wave, plateformes cloud à polling) continuent de restaurer des entités et
    de les faire sortir de unavailable/unknown bien après ce point (observé sur
    une instance réelle : le nombre total d'états grimpait encore ~35 s après le
    démarrage).

    On suit l'ensemble réel des entity_ids unavailable/unknown (plus le nombre
    total d'entités, pour attraper les entités nouvellement enregistrées déjà
    disponibles) plutôt qu'un simple compteur : deux entités qui se croisent
    (l'une revient pendant qu'une autre tombe) laisseraient un compteur inchangé
    alors que l'instance bouge encore beaucoup. Dès que cette signature n'a pas
    changé pendant SETTLE_QUIET_SECONDS — et qu'au moins SETTLE_MIN_SECONDS se
    sont écoulées —, on considère que c'est stable. ceiling_seconds reste un
    plafond dur pour qu'une entité réellement et définitivement cassée ne puisse
    pas repousser le scan indéfiniment : elle sera simplement rapportée une fois
    le plafond atteint, comme avant. Un plafond réglé sous SETTLE_MIN_SECONDS
    l'emporte, ce qui permet de forcer un scan précoce.
    """
    start = monotonic()
    deadline = start + ceiling_seconds
    last_signature: tuple[int, frozenset[str]] | None = None
    changed_at = start

    while True:
        now = monotonic()
        states = hass.states.async_all()
        unavailable_ids = frozenset(
            st.entity_id for st in states
            if st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
        )
        signature = (len(states), unavailable_ids)

        if signature != last_signature:
            last_signature = signature
            changed_at = now
        elif (
            now - changed_at >= SETTLE_QUIET_SECONDS
            and now - start >= SETTLE_MIN_SECONDS
        ):
            _LOGGER.info(
                "HACA: entity states settled (%d entities, %d unavailable/unknown) "
                "after %.0fs — running initial scan",
                len(states), len(unavailable_ids), now - start,
            )
            return

        if now >= deadline:
            _LOGGER.info(
                "HACA: startup settle ceiling (%ds) reached before states stopped "
                "changing (%d entities, %d unavailable/unknown) — running initial "
                "scan anyway",
                ceiling_seconds, len(states), len(unavailable_ids),
            )
            return

        await asyncio.sleep(SETTLE_POLL_SECONDS)



# ─── Scan timings ─────────────────────────────────────────────────────────
# Audit 5-3 asks whether the scan blocks Home Assistant long enough to be
# worth moving off the event loop. Nothing in the package measured it, so the
# plan's "10 to 30 seconds" was an estimate. ScanTimer records how long each
# stage of a scan takes and logs one line per scan, so that decision can be
# made from the user's own installation instead of from a guess.


class ScanTimer:
    """Wall-clock timings for one scan, and the log line they produce.

    ``stage()`` is for the sequential parts: their durations add up to the
    total, and whatever is left over is reported as ``other`` — the untimed
    glue between stages, which is pure Python on the event loop and therefore
    exactly what 5-3 is about.

    ``overlapping()`` is for the six analyzers inside the ``asyncio.gather``
    phase. Each one's clock keeps running while its siblings hold the loop, so
    those numbers must never be summed; the phase as a whole is timed with
    ``stage()``, and the breakdown goes to DEBUG with the caveat attached.

    Neither of those answers the question 5-3 actually asks. A stage takes
    wall-clock time both while it holds the loop and while it waits its turn
    on a busy one, and only the first is a freeze. ``start_loop_probe()``
    separates them: a task that asks to be woken every 50 ms and records how
    late it actually was. A wake-up three seconds late means the loop ran
    nothing for three seconds — that is the freeze, measured directly.
    """

    # A stage quicker than this is folded into the total and not named: on a
    # small installation most of them are, and a line of twelve "0.0s" hides
    # the one entry that matters.
    MIN_REPORTED_SECONDS = 0.1

    # The probe asks to be woken this often. Frequent enough to catch a short
    # freeze, rare enough to cost nothing: it can only run when the loop is
    # already free, which is precisely what it is there to measure.
    LOOP_PROBE_INTERVAL = 0.05

    # Below this, a late wake-up is scheduler jitter, not a freeze — and a
    # 50 ms stall is not something anyone sees in the interface.
    LOOP_STALL_FLOOR = 0.05

    # The probe is cancelled when the scan ends. This is the belt to that
    # braces: should the scan raise somewhere the analyzers do not already
    # guard, the task ends by itself instead of waking forever.
    MAX_PROBE_SECONDS = 600.0

    def __init__(self, subject: str = "scan", *, quiet_below: float = 0.0) -> None:
        """Time one run of ``subject``.

        ``quiet_below`` sends the summary to DEBUG when the whole run came in
        under that many seconds. A scan always reports it (0.0): that line is
        the measurement 5-3 is decided on. A breakdown *inside* one stage only
        earns an INFO line when that stage was slow enough to be felt —
        otherwise it is detail, and detail on every scan is noise.
        """
        self._subject = subject
        self._quiet_below = quiet_below
        self._started = monotonic()
        self._stages: dict[str, float] = {}
        self._overlapping: dict[str, float] = {}
        self._current: str | None = None
        self._probe: asyncio.Task | None = None
        self._probe_ran = False
        self._stalls = 0
        self._stalled_for = 0.0
        self._worst_stall = 0.0
        self._worst_stall_stage = ""

    @contextmanager
    def stage(self, label: str):
        """Time one sequential stage, whether it returns or raises."""
        start = monotonic()
        previous, self._current = self._current, label
        try:
            yield
        finally:
            self._current = previous
            self._stages[label] = self._stages.get(label, 0.0) + (monotonic() - start)

    @contextmanager
    def overlapping(self, label: str):
        """Time one analyzer that shares the loop with its siblings."""
        start = monotonic()
        try:
            yield
        finally:
            self._overlapping[label] = (
                self._overlapping.get(label, 0.0) + (monotonic() - start)
            )

    async def _probe_the_loop(self) -> None:
        """Ask to be woken every 50 ms and record how late each wake-up is.

        Lateness is the whole measurement. The loop can only run this task
        when nothing else holds it, so a wake-up that is late by N seconds is
        N seconds during which Home Assistant answered nothing: no automation
        fired, no state updated, no page rendered.

        A stall is blamed on the stage that was running when the probe asked
        to be woken — that stage is the one that failed to wake it. Reading
        the stage on waking instead would blame the wrong one: the loop runs
        the task that yielded before it runs this one, so by then the stage
        has often already ended. The attribution is still approximate at a
        stage boundary, and exact anywhere inside a stage that yields — which
        is what the two long ones do, every 20 to 50 items.

        The individual analyzers inside the gather phase are deliberately not
        named: six coroutines interleave there, so blaming one would be a
        guess. A stall there belongs to the phase.
        """
        give_up_at = monotonic() + self.MAX_PROBE_SECONDS
        while monotonic() < give_up_at:
            due = monotonic() + self.LOOP_PROBE_INTERVAL
            running = self._current
            await asyncio.sleep(self.LOOP_PROBE_INTERVAL)
            late_by = monotonic() - due
            if late_by < self.LOOP_STALL_FLOOR:
                continue
            self._stalls += 1
            self._stalled_for += late_by
            if late_by > self._worst_stall:
                self._worst_stall = late_by
                self._worst_stall_stage = (
                    running or self._current or "between stages"
                )

    def start_loop_probe(self) -> None:
        """Begin watching the loop. Call once, at the top of the scan."""
        self._probe_ran = True
        self._probe = asyncio.get_running_loop().create_task(self._probe_the_loop())

    async def stop_loop_probe(self) -> None:
        """Stop watching. Safe to call whether or not the probe was started."""
        if self._probe is None:
            return
        self._probe.cancel()
        with suppress(asyncio.CancelledError):
            await self._probe
        self._probe = None

    @classmethod
    def _ranked(cls, durations: dict[str, float]) -> str:
        """Slowest first — the culprit should be the first thing read."""
        return " · ".join(
            f"{label} {secs:.1f}s"
            for label, secs in sorted(
                durations.items(), key=lambda kv: kv[1], reverse=True
            )
            if secs >= cls.MIN_REPORTED_SECONDS
        )

    def log(self) -> None:
        """Emit the timings: one INFO line, the gather breakdown at DEBUG."""
        total = monotonic() - self._started
        reported = dict(self._stages)
        reported["other"] = max(0.0, total - sum(self._stages.values()))
        _LOGGER.log(
            logging.DEBUG if total < self._quiet_below else logging.INFO,
            "HACA: %s finished in %.1fs — %s",
            self._subject,
            total,
            self._ranked(reported) or "every stage under 0.1s",
        )
        if self._probe_ran:
            if self._stalls:
                _LOGGER.info(
                    "HACA: the event loop was blocked %.1fs of that scan, over "
                    "%d stalls — worst single freeze %.1fs, during %s",
                    self._stalled_for, self._stalls, self._worst_stall,
                    self._worst_stall_stage,
                )
            else:
                _LOGGER.info(
                    "HACA: the event loop was never blocked for more than %dms "
                    "during that scan — the time above was spent waiting, not "
                    "holding it",
                    int(self.LOOP_STALL_FLOOR * 1000),
                )
        if self._overlapping:
            _LOGGER.debug(
                "HACA: parallel phase, per analyzer (wall clock — these overlap "
                "and do not add up to the phase) — %s",
                self._ranked(self._overlapping) or "every analyzer under 0.1s",
            )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the H.A.C.A component.

    Card registration happens here (not in async_setup_entry) because:
    - It must run exactly once per integration domain
    - manifest.json declares dependencies: ["frontend", "http"]
      so these components are guaranteed to be loaded
    """
    hass.data.setdefault(DOMAIN, {})

    # Register Lovelace card resources as early as possible: the frontend
    # imports the resource list once per page load, so a resource that lands
    # after the browser connected stays unknown for that whole session
    # ("Custom element not found: haca-dashboard-card").
    async def _setup_cards(_event=None) -> None:
        try:
            await async_register_cards(hass)
        except Exception as exc:
            _LOGGER.warning("[HACA] Card registration failed: %s", exc)

    await _setup_cards()
    # Retried once HA is fully started, in case `lovelace` was not ready yet.
    # async_register_cards() is idempotent, so this is a no-op if it worked.
    hass.bus.async_listen_once("homeassistant_started", _setup_cards)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bring an older config entry up to the current schema.

    minor_version 1 → 2 (1.8.0): the MCP server, the proactive agent and the LLM
    API became options and now default to off. An entry still at 1 was created
    before that, when all three ran unconditionally, so it is given an explicit
    True — upgrading H.A.C.A must not silently switch off a server somebody is
    talking to. New entries are created at 2 and get the off defaults.
    """
    if entry.version > 1:
        # Written by a newer H.A.C.A than the one running: refuse rather than
        # guess what its data means.
        return False

    if entry.minor_version < 2:
        options = dict(entry.options)
        for key in (OPT_MCP_SERVER_ENABLED, OPT_PROACTIVE_AGENT_ENABLED, OPT_LLM_API_ENABLED):
            options.setdefault(key, True)
        hass.config_entries.async_update_entry(
            entry, options=options, version=1, minor_version=2
        )
        _LOGGER.info(
            "[HACA] Config entry migrated to 1.2 — MCP server, proactive agent and "
            "LLM API kept enabled (they were always on before 1.8.0; new installs "
            "start with them off)."
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up H.A.C.A from a config entry."""
    _LOGGER.info("Setting up %s v%s", NAME, VERSION)

    hass.data.setdefault(DOMAIN, {})

    # Pré-charger le cache de traductions (évite tout I/O bloquant dans l'event loop)
    await _async_preload_ts_cache(hass)

    # ── Migrate default excluded_issue_types for existing installations ──
    # New installs get these defaults via config_flow, but users who
    # installed before v1.6.3 don't.  Merge missing defaults once.
    _DEFAULT_EXCLUDED_TYPES = {
        "no_description", "no_alias",
        "helper_no_friendly_name", "helper_orphaned_disabled_only",
        "helper_unused", "unused_input_boolean",
        "script_orphan", "script_blueprint_candidate",
        "scene_not_triggered", "timer_orphaned",
        "template_sensor_no_metadata", "template_missing_availability",
        "missing_state_class", "group_nested_deep",
    }
    current_excluded = set(entry.options.get("excluded_issue_types", []))
    missing_defaults = _DEFAULT_EXCLUDED_TYPES - current_excluded
    if missing_defaults:
        new_excluded = sorted(current_excluded | _DEFAULT_EXCLUDED_TYPES)
        new_options = {**entry.options, "excluded_issue_types": new_excluded}
        hass.config_entries.async_update_entry(entry, options=new_options)
        _LOGGER.info("Migrated excluded_issue_types: added %s", missing_defaults)

    # ── Refresh ``notification_language_auto`` from the owner's frontend
    # profile language. The panel handshake also writes this option, but
    # it can lag behind a profile change (the user must re-open the panel
    # to trigger a handshake). Reading directly from ``.storage/frontend.user_data_*``
    # at startup ensures notifications use the current profile language
    # even before the panel is mounted again. Only an explicit
    # ``notification_language`` (set by the user from Configuration) takes
    # precedence over this auto value.
    try:
        from .translation_utils import async_detect_frontend_user_language
        detected_lang = await async_detect_frontend_user_language(hass)
        if detected_lang:
            cur_auto = entry.options.get("notification_language_auto")
            if cur_auto != detected_lang:
                new_options = {**entry.options, "notification_language_auto": detected_lang}
                hass.config_entries.async_update_entry(entry, options=new_options)
                _LOGGER.info(
                    "[HACA] notification_language_auto refreshed from frontend storage: %s -> %s",
                    cur_auto, detected_lang,
                )
    except Exception as exc:
        _LOGGER.debug("[HACA] could not refresh notification language at startup: %s", exc)

    if entry.entry_id in hass.data[DOMAIN]:
        _LOGGER.warning("H.A.C.A already set up for this entry")
        return True
    
    # Create analyzers
    automation_analyzer = AutomationAnalyzer(hass)
    entity_analyzer = EntityAnalyzer(hass)
    battery_monitor = BatteryMonitor(
        hass,
        critical=entry.options.get("battery_critical", 5),
        low=entry.options.get("battery_low", 15),
        warning=entry.options.get("battery_warning", 25),
    )
    dependency_mapper = DependencyMapper(hass)
    automation_optimizer = AutomationOptimizer(hass)
    performance_analyzer = PerformanceAnalyzer(hass)
    security_analyzer = SecurityAnalyzer(hass)
    dashboard_analyzer = DashboardAnalyzer(hass) if MODULE_9_DASHBOARD_ANALYZER else None
    recorder_analyzer = RecorderAnalyzer(hass) if MODULE_11_RECORDER_ANALYZER else None
    history_manager = HistoryManager(
        hass,
        retention_days=entry.options.get("history_retention_days", 365),
    ) if MODULE_12_AUDIT_HISTORY else None
    
    # Create optional modules
    report_generator = ReportGenerator(hass) if MODULE_4_COMPLIANCE_REPORT else None
    refactoring_assistant = RefactoringAssistant(hass) if MODULE_5_REFACTORING_ASSISTANT else None
    compliance_analyzer = ComplianceAnalyzer(hass) if MODULE_17_COMPLIANCE_ANALYZER else None

    # ── v1.5.0 analyzers ──────────────────────────────────────────────────
    battery_predictor = BatteryPredictor(hass) if MODULE_18_BATTERY_PREDICTOR else None
    area_complexity_analyzer = AreaComplexityAnalyzer(hass) if MODULE_19_AREA_COMPLEXITY else None
    redundancy_analyzer = RedundancyAnalyzer(hass) if MODULE_20_REDUNDANCY_ANALYZER else None
    recorder_impact_analyzer = RecorderImpactAnalyzer(hass) if MODULE_21_RECORDER_IMPACT else None
    integration_analyzer = IntegrationAnalyzer(hass) if MODULE_22_INTEGRATION_MONITOR else None
    
    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    
    async def async_update_data() -> dict[str, Any]:
        """Update data."""
        _LOGGER.debug("Running scheduled scan")
        timer = ScanTimer()
        timer.start_loop_probe()

        # Seven analyzers ask for the haca_ignore set. Opening the window here
        # means one registry walk per scan instead of one per analyzer; the
        # slot is reset at every refresh, so a label added between two scans is
        # picked up by the next one.
        from .translation_utils import begin_haca_ignore_scan
        begin_haca_ignore_scan(hass)

        # Catégories exclues configurées dans le panel HACA
        excluded: set = set(entry.options.get("excluded_categories", []))

        # analyze_all() fills the analyzer's own issue lists, read back below;
        # its return value is not needed here.
        try:
            if "automations" not in excluded:
                with timer.stage("automations"):
                    await automation_analyzer.analyze_all()
        except Exception as _auto_err:
            _LOGGER.error(
                "HACA: automation_analyzer.analyze_all() CRASHED — %s",
                _auto_err, exc_info=True,
            )

        try:
            with timer.stage("entities"):
                entity_issues = (
                    await entity_analyzer.analyze_all(
                        automation_analyzer.automation_configs,
                        automation_analyzer.script_configs,
                    )
                    if "entities" not in excluded else []
                )
        except Exception as _ent_err:
            _LOGGER.error(
                "HACA: entity_analyzer.analyze_all() CRASHED — %s",
                _ent_err, exc_info=True,
            )
            entity_issues = []

        # ── Phase 2: parallel analysis ────────────────────────────────────
        # All analyzers below depend on automation_analyzer results (already
        # available) but are independent of each other.  Running them with
        # asyncio.gather reduces total scan time by 40-60% on large setups.

        async def _safe_perf() -> list:
            if "performance" in excluded:
                return []
            with timer.overlapping("performance"):
                return await performance_analyzer.analyze_all(
                    automation_analyzer.automation_configs
                )

        async def _safe_security() -> list:
            if "security" in excluded:
                return []
            with timer.overlapping("security"):
                return await security_analyzer.analyze_all(
                    automation_analyzer.automation_configs
                )

        async def _safe_dashboard() -> list:
            if not dashboard_analyzer or "dashboards" in excluded:
                return []
            with timer.overlapping("dashboards"):
                return await dashboard_analyzer.analyze_all()

        async def _safe_battery() -> list:
            if "batteries" in excluded:
                return []
            with timer.overlapping("batteries"):
                return await battery_monitor.analyze_all(
                    critical=entry.options.get("battery_critical", 5),
                    low=entry.options.get("battery_low", 15),
                    warning=entry.options.get("battery_warning", 25),
                )

        async def _safe_recorder() -> tuple[list, float]:
            if not recorder_analyzer or "recorder" in excluded:
                return [], 0.0
            with timer.overlapping("recorder"):
                orphans = await recorder_analyzer.analyze_all()
            return orphans, recorder_analyzer.total_wasted_mb

        async def _safe_compliance() -> list:
            if not compliance_analyzer or "compliance" in excluded:
                return []
            with timer.overlapping("compliance"):
                return await compliance_analyzer.async_analyze()

        with timer.stage("parallel phase"):
            results = await asyncio.gather(
                _safe_perf(),
                _safe_security(),
                _safe_dashboard(),
                _safe_battery(),
                _safe_recorder(),
                _safe_compliance(),
                return_exceptions=True,
            )

        # Unpack results with safe fallbacks for exceptions
        performance_issues = results[0] if not isinstance(results[0], BaseException) else []
        security_issues    = results[1] if not isinstance(results[1], BaseException) else []
        dashboard_issues   = results[2] if not isinstance(results[2], BaseException) else []
        battery_list       = results[3] if not isinstance(results[3], BaseException) else []
        recorder_result    = results[4] if not isinstance(results[4], BaseException) else ([], 0.0)
        compliance_issues  = results[5] if not isinstance(results[5], BaseException) else []

        # Log any exceptions from parallel phase
        for idx, (label, res) in enumerate([
            ("performance", results[0]), ("security", results[1]),
            ("dashboard", results[2]), ("battery", results[3]),
            ("recorder", results[4]), ("compliance", results[5]),
        ]):
            if isinstance(res, BaseException):
                _LOGGER.error("HACA: %s analyzer CRASHED — %s", label, res, exc_info=res)

        recorder_orphans: list = recorder_result[0]
        recorder_wasted_mb: float = recorder_result[1]

        # ── Post-parallel filtering ───────────────────────────────────────
        excluded_types: set = set(entry.options.get("excluded_issue_types", []))
        if excluded_types and compliance_issues:
            compliance_issues = [i for i in compliance_issues if i.get("type", "") not in excluded_types]

        # Get separated issue lists from automation analyzer
        automation_only_issues = automation_analyzer.automation_issues
        script_issues = automation_analyzer.script_issues
        scene_issues = automation_analyzer.scene_issues
        blueprint_issues = automation_analyzer.blueprint_issues

        # Get helper issues separated by entity_analyzer
        helper_issues = getattr(entity_analyzer, "helper_issues", [])

        # Route scene.* issues from entity_analyzer into scene_issue_list
        # (entity_analyzer produces unavailable/stale/zombie issues for scene.* that
        #  belong in the Scenes tab, not the Entities tab)
        entity_scene_issues = [i for i in entity_issues if i.get("entity_id", "").startswith("scene.")]
        entity_issues       = [i for i in entity_issues if not i.get("entity_id", "").startswith("scene.")]
        scene_issues        = scene_issues + entity_scene_issues

        # Filtrage par type d'issue (configuré dans le panel HACA → onglet Configuration)
        if excluded_types:
            def _filter(lst):
                return [i for i in lst if i.get("type", "") not in excluded_types]
            automation_only_issues = _filter(automation_only_issues)
            script_issues          = _filter(script_issues)
            scene_issues           = _filter(scene_issues)
            blueprint_issues       = _filter(blueprint_issues)
            entity_issues          = _filter(entity_issues)
            helper_issues          = _filter(helper_issues)
            performance_issues     = _filter(performance_issues)
            security_issues        = _filter(security_issues)
            dashboard_issues       = _filter(dashboard_issues)

        # ── Tag each issue with a stable haca_id for frontend display ─────
        # Built from invariant fields only (entity_id/alias, type, location)
        # so the same logical issue keeps the same id across scans and
        # language switches. The id is used for click-to-copy badges in the
        # panel and to identify issues in the AI explain / redundancy /
        # compliance views — it is NOT used to drive any dismissal feature.
        import hashlib as _hl

        def _tag_ids(issue_list: list, cat_code: str) -> list:
            for issue in issue_list:
                eid = issue.get("entity_id") or issue.get("alias") or "unknown"
                itype = (issue.get("type") or "unknown").upper()
                loc = issue.get("location") or ""
                signature = f"{eid}|{itype}|{loc}"
                h = _hl.md5(signature.encode("utf-8", "replace")).hexdigest()[:8]
                issue["haca_id"] = f"HACA-{cat_code}-{itype}-{h}"
            return issue_list

        _tag_ids(automation_only_issues, "AUTO")
        _tag_ids(script_issues, "SCRIPT")
        _tag_ids(scene_issues, "SCENE")
        _tag_ids(blueprint_issues, "BP")
        _tag_ids(entity_issues, "ENT")
        _tag_ids(helper_issues, "HELPER")
        _tag_ids(performance_issues, "PERF")
        _tag_ids(security_issues, "SEC")
        _tag_ids(dashboard_issues, "DASH")
        _tag_ids(compliance_issues, "COMPL")

        # ── v1.5.0 — Battery prediction ───────────────────────────────────
        battery_predictions: list = []
        if battery_predictor and battery_list:
            try:
                with timer.stage("battery predictions"):
                    await battery_predictor.async_save_battery_snapshot(battery_list)
                    battery_predictions = await battery_predictor.async_compute_predictions(battery_list)
            except Exception as bp_err:
                _LOGGER.warning("Battery predictor error: %s", bp_err)

        # ── v1.5.0 — Area complexity heatmap ──────────────────────────────
        area_complexity_data: dict = {}
        if area_complexity_analyzer:
            try:
                with timer.stage("area complexity"):
                    area_complexity_data = await area_complexity_analyzer.async_analyze(
                        automation_configs=automation_analyzer.automation_configs,
                        complexity_scores=automation_analyzer.complexity_scores,
                    )
            except Exception as ac_err:
                _LOGGER.warning("Area complexity analyzer error: %s", ac_err)

        # ── v1.5.0 — Redundancy analysis ──────────────────────────────────
        redundancy_data: dict = {}
        if redundancy_analyzer:
            try:
                with timer.stage("redundancy"):
                    redundancy_data = await redundancy_analyzer.async_analyze(
                        automation_configs=automation_analyzer.automation_configs,
                        blueprint_stats=automation_analyzer.blueprint_stats,
                        complexity_scores=automation_analyzer.complexity_scores,
                    )
            except Exception as red_err:
                _LOGGER.warning("Redundancy analyzer error: %s", red_err)

        # ── Flatten redundancy into a standard issue list ─────────────────
        redundancy_issue_list: list[dict] = []
        for item in redundancy_data.get("blueprint_matches", []):
            item["type"] = "redundancy_blueprint_candidate"
            item["fix_available"] = True
            item["message"] = f"Could be replaced by blueprint: {item.get('blueprint_id', '?')}"
            item["recommendation"] = "Use AI to create a blueprint and convert this automation"
            redundancy_issue_list.append(item)
        for item in redundancy_data.get("native_feature_matches", []):
            item["type"] = "redundancy_native_replacement"
            item["fix_available"] = True
            item["message"] = f"Can be replaced by native HA feature: {item.get('description') or item.get('pattern', '?')}"
            item["recommendation"] = "Use AI to refactor this automation using the native HA feature"
            redundancy_issue_list.append(item)
        for item in redundancy_data.get("trigger_overlaps", []):
            item["type"] = "redundancy_trigger_overlap"
            item["entity_id"] = item.get("entity_id_a", "")
            item["alias"] = f"{item.get('alias_a', '')} ↔ {item.get('alias_b', '')}"
            item["fix_available"] = False
            item["message"] = f"Trigger overlap with {item.get('alias_b', '?')}: {item.get('trigger_sig', '?')}"
            item["recommendation"] = "Review both automations to determine if they conflict or should be merged"
            redundancy_issue_list.append(item)
        _tag_ids(redundancy_issue_list, "REDUND")

        # Build recorder-impact data BEFORE the ignore-marking pass so its
        # exclude_suggestions can also be tagged and dismissed individually.
        recorder_impact_data: dict = {}
        if recorder_impact_analyzer:
            try:
                with timer.stage("recorder impact"):
                    recorder_impact_data = await recorder_impact_analyzer.async_analyze(
                        automation_configs=automation_analyzer.automation_configs,
                        complexity_scores=automation_analyzer.complexity_scores,
                    )
            except Exception as ri_err:
                _LOGGER.warning("Recorder impact analyzer error: %s", ri_err)

        # ── Health score, stat-card counts, history snapshot ─────────────
        total_entities     = len(hass.states.async_all())
        total_automations  = len(automation_analyzer.automation_configs) + len(automation_analyzer.script_configs)
        health_score = calculate_health_score(
            automation_only_issues, entity_issues,
            performance_issues, security_issues, dashboard_issues,
            total_entities=total_entities,
            total_automations=total_automations,
            helper_issues=helper_issues,
            compliance_issues=compliance_issues,
            script_issues=script_issues,
            scene_issues=scene_issues,
            blueprint_issues=blueprint_issues,
        )
        _LOGGER.info(
            "Health Score Calculation: Automation=%d, Scripts=%d, Blueprints=%d, Entities=%d, Helpers=%d, Performance=%d, Dashboard=%d. Score=%d%%",
            len(automation_only_issues), len(script_issues), len(blueprint_issues),
            len(entity_issues), len(helper_issues),
            len(performance_issues), len(dashboard_issues), health_score,
        )

        scan_result = {
            "health_score":        health_score,
            "total_issues":        len(automation_only_issues) + len(script_issues)
                                 + len(scene_issues) + len(blueprint_issues)
                                 + len(entity_issues) + len(helper_issues)
                                 + len(performance_issues) + len(security_issues)
                                 + len(dashboard_issues),
            "automation_issues":   len(automation_only_issues),
            "script_issues":       len(script_issues),
            "scene_issues":        len(scene_issues),
            "entity_issues":       len(entity_issues),
            "helper_issues":       len(helper_issues),
            "performance_issues":  len(performance_issues),
            "security_issues":     len(security_issues),
            "blueprint_issues":    len(blueprint_issues),
            "dashboard_issues":    len(dashboard_issues),
        }
        if history_manager:
            try:
                with timer.stage("history"):
                    await history_manager.async_save_scan(scan_result)
            except Exception as hist_err:
                _LOGGER.warning("HACA History save error: %s", hist_err)

        # Build dependency graph
        dependency_graph = {"nodes": [], "edges": []}
        try:
            all_flat_issues = (
                automation_only_issues + script_issues + scene_issues +
                blueprint_issues + entity_issues + helper_issues + performance_issues +
                security_issues + dashboard_issues
            )
            with timer.stage("dependency graph"):
                dependency_graph = await dependency_mapper.build(
                    automation_configs=automation_analyzer.automation_configs,
                    script_configs=automation_analyzer.script_configs,
                    scene_configs=automation_analyzer.scene_configs,
                    # Explicit `entity_id:` references only. The full map also
                    # holds the entities reached through an `area_id` /
                    # `label_id` target, which is right for "is this entity
                    # used?" but would add one graph edge per entity of the
                    # area — a rendered graph that grows with the size of the
                    # house rather than with the config.
                    entity_references=dict(entity_analyzer.strong_entity_references),
                    alias_map=entity_analyzer.automation_alias_map,
                    all_issues=all_flat_issues,
                )
        except Exception as dep_err:
            _LOGGER.error("Dependency mapper error: %s", dep_err)

        await timer.stop_loop_probe()
        timer.log()

        return {
            "health_score": health_score,
            "automation_issues": len(automation_only_issues),
            "script_issues":     len(script_issues),
            "scene_issues":      len(scene_issues),
            "blueprint_issues":  len(blueprint_issues),
            "entity_issues":     len(entity_issues),
            "helper_issues":     len(helper_issues),
            "performance_issues": len(performance_issues),
            "security_issues":   len(security_issues),
            "dashboard_issues":  len(dashboard_issues),
            "total_issues":      len(automation_only_issues) + len(script_issues)
                               + len(scene_issues) + len(blueprint_issues)
                               + len(entity_issues) + len(helper_issues)
                               + len(performance_issues) + len(security_issues)
                               + len(dashboard_issues) + len(compliance_issues),
            "compliance_issues": len(compliance_issues),
            "compliance_issue_list": compliance_issues,
            "automation_issue_list": automation_only_issues,
            "complexity_scores":        sorted(automation_analyzer.complexity_scores, key=lambda x: x["score"], reverse=True) if automation_analyzer else [],
            "script_complexity_scores": automation_analyzer.script_complexity_scores if automation_analyzer else [],
            "scene_stats":              automation_analyzer.scene_stats if automation_analyzer else [],
            "blueprint_stats":          automation_analyzer.blueprint_stats if automation_analyzer else [],
            "script_issue_list": script_issues,
            "scene_issue_list": scene_issues,
            "blueprint_issue_list": blueprint_issues,
            "entity_issue_list": entity_issues,
            "helper_issue_list": helper_issues,
            "performance_issue_list": performance_issues,
            "security_issue_list": security_issues,
            "dashboard_issue_list": dashboard_issues,
            "recorder_orphans": recorder_orphans,
            "recorder_orphan_count": len(recorder_orphans),
            "recorder_wasted_mb": recorder_wasted_mb,
            "recorder_db_available": getattr(recorder_analyzer, "db_available", False),
            "battery_list": battery_list,
            "battery_count": len(battery_list),
            "battery_alerts": sum(1 for b in battery_list if b["severity"] is not None),
            "battery_alert_entities": [
                {"entity_id": b["entity_id"], "level": b["level"], "unit": b.get("unit", "%"),
                 "device_class": b.get("device_class", ""), "severity": b["severity"]}
                for b in battery_list if b["severity"] is not None
            ],
            "dependency_graph": dependency_graph,
            # ── v1.5.0 ────────────────────────────────────────────────────
            "battery_predictions": battery_predictions,
            "battery_predictions_count": len(battery_predictions),
            "battery_alert_7d": sum(1 for p in battery_predictions if p.get("alert_7d")),
            "area_complexity": area_complexity_data,
            "redundancy": redundancy_data,
            "redundancy_issue_list": redundancy_issue_list,
            "recorder_impact": recorder_impact_data,
            "last_scan": _dt_util.utcnow().isoformat(),
        }
    
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=scan_interval) if scan_interval > 0 else None,
    )

    # ── Tell the panel when a scan lands ──────────────────────────────────
    # `haca_scan_complete` used to be fired only by the manual scan paths, so
    # the panel had no way of knowing a scheduled scan had produced new data
    # and polled `haca/get_data` every 60 seconds — for data that changes once
    # an hour. Firing it here as well lets the panel refresh on the event and
    # keep the timer as a mere safety net.
    @callback
    def _fire_scan_complete() -> None:
        hass.bus.async_fire("haca_scan_complete", {
            "entry_id": entry.entry_id,
            "success": True,
            "scheduled": True,
        })

    unsub_scan_complete = coordinator.async_add_listener(_fire_scan_complete)
    
    # In-memory state-change counter — see noisy_tracker.py for why this
    # exists. Listens to EVENT_STATE_CHANGED so HACA can flag noisy
    # entities even when HA's recorder is currently filtering them
    # (otherwise the SQL query has nothing to find for ~24h after the
    # user un-excludes an entity in configuration.yaml).
    #
    # The listener sees every state change on the instance, so it only runs
    # while the noisy-entity scan is switched on (panel → Configuration →
    # Performance → "Noisy entity"). haca/save_options starts/stops it live.
    from .noisy_tracker import NoisyEntityTracker
    from .performance_analyzer import noisy_scan_enabled
    noisy_tracker = NoisyEntityTracker(hass)
    if noisy_scan_enabled(hass):
        noisy_tracker.start()
    else:
        _LOGGER.debug("[HACA] noisy-entity scan disabled — tracker not started")

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "entry": entry,
        "_unsub_scan_complete": unsub_scan_complete,
        "_scan_in_progress": False,
        "automation_analyzer": automation_analyzer,
        "entity_analyzer": entity_analyzer,
        "performance_analyzer": performance_analyzer,
        "report_generator": report_generator,
        "refactoring_assistant": refactoring_assistant,
        "security_analyzer": security_analyzer,
        "dashboard_analyzer": dashboard_analyzer,
        "recorder_analyzer": recorder_analyzer,
        "history_manager": history_manager,
        "battery_predictor": battery_predictor,
        "automation_optimizer": automation_optimizer,
        "compliance_analyzer": compliance_analyzer,
        "integration_analyzer": integration_analyzer,
        "noisy_tracker": noisy_tracker,
    }
    
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=NAME,
        manufacturer="Community",
        model="Config Auditor",
        sw_version=VERSION,
    )
    
    # ── Deferred first scan ───────────────────────────────────────────────
    # Do NOT run async_config_entry_first_refresh() immediately: HA may still
    # be loading other integrations (zigbee, zwave, mqtt…) so entities would
    # appear unavailable / missing, generating false-positive issues.
    #
    # Instead, set an empty initial coordinator state now (so sensors register
    # without blocking), then schedule the real first scan to run only after
    # EVENT_HOMEASSISTANT_STARTED — i.e. when every integration is loaded.
    coordinator.data = {
        "health_score": 0,
        "total_issues": 0,
        "automation_issues": 0,
        "script_issues": 0,
        "scene_issues": 0,
        "entity_issues": 0,
        "helper_issues": 0,
        "performance_issues": 0,
        "security_issues": 0,
        "blueprint_issues": 0,
        "automation_issue_list": [],
        "script_issue_list": [],
        "scene_issue_list": [],
        "entity_issue_list": [],
        "helper_issue_list": [],
        "performance_issue_list": [],
        "security_issue_list": [],
        "blueprint_issue_list": [],
        "dashboard_issues": 0,
        "dashboard_issue_list": [],
        "compliance_issues": 0,
        "compliance_issue_list": [],
        "recorder_orphans": [],
        "recorder_orphan_count": 0,
        "recorder_wasted_mb": 0.0,
        "recorder_db_available": False,
        "complexity_scores": [],
        "script_complexity_scores": [],
        "scene_stats": [],
        "blueprint_stats": [],
        "battery_list": [],
        "battery_count": 0,
        "battery_alerts": 0,
        "dependency_graph": {"nodes": [], "edges": []},
        "battery_predictions": [],
        "battery_predictions_count": 0,
        "battery_alert_7d": 0,
        "area_complexity": {},
        "redundancy": {},
        "redundancy_issue_list": [],
        "recorder_impact": {},
    }

    async def _first_scan_when_ready(hass_: HomeAssistant) -> None:
        """Run the very first HACA scan after HA has fully started.

        Even after EVENT_HOMEASSISTANT_STARTED some integrations (Zigbee,
        Z-Wave, cloud platforms) continue restoring entities asynchronously.
        We watch the state machine until it stops changing before scanning, so
        those entities are present and won't be reported as false-positive
        issues. startup_delay_seconds is the ceiling of that wait, not a fixed
        sleep: a fast boot scans as soon as things are stable, a slow one is
        still capped.
        """
        # Check if startup scan is disabled
        startup_scan = entry.options.get("startup_scan_enabled",
                       entry.data.get("startup_scan_enabled", True))
        if not startup_scan:
            _LOGGER.info("HACA startup scan disabled by configuration")
            return

        startup_delay = int(
            entry.options.get("startup_delay_seconds",
            entry.data.get("startup_delay_seconds", 60))
        )
        if startup_delay > 0:
            _LOGGER.info(
                "Home Assistant started — HACA waiting up to %ds for entity "
                "states to settle before the initial scan",
                startup_delay,
            )
            await _wait_for_entities_to_settle(hass_, startup_delay)

        _LOGGER.info("Running HACA initial scan now")
        try:
            await coordinator.async_refresh()
        except Exception as exc:
            _LOGGER.warning("HACA initial scan error: %s", exc)

    entry.async_on_unload(async_at_started(hass, _first_scan_when_ready))
    # ──────────────────────────────────────────────────────────────────────

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register panel - CORRECTION: enregistrer le panneau seulement pour la première instance
    if len([e for e in hass.config_entries.async_entries(DOMAIN)]) == 1:
        await async_register_panel(hass)
        async_register_websocket_handlers(hass)
        await async_setup_conversation(hass, entry)
        _LOGGER.info("Panel, WebSocket handlers and Conversation agent registered")
    
    if len([e for e in hass.config_entries.async_entries(DOMAIN)]) == 1:
        await async_setup_services(hass, entry)
    
    # NOTE: Pas de update_listener → async_reload_entry.
    # async_update_entry (appelé dans handle_save_options) met à jour entry.options
    # sans déclencher de reload. Le coordinator relit entry.options à chaque scan.
    # Un reload complet (non déclenché automatiquement) reste possible via l'UI HA
    # pour appliquer scan_interval et event_monitoring immédiatement.
    
    # ── Event-Based Monitoring (MODULE 10) ───────────────────────────────
    if MODULE_10_EVENT_MONITORING:
        async_setup_event_monitor(hass, entry)
    # ── End Event-Based Monitoring ────────────────────────────────────────

    # ── v1.4.0 : Serveur MCP (MODULE 15) ─────────────────────────────────
    # Trois surfaces sensibles, chacune commandée par une option du panneau et
    # désactivée sur une installation neuve (voir const.py). Une entrée créée
    # avant 1.8.0 est passée à True par async_migrate_entry, donc rien ne
    # s'éteint sur une mise à jour.
    if MODULE_15_MCP_SERVER and entry.options.get(
        OPT_MCP_SERVER_ENABLED, DEFAULT_MCP_SERVER_ENABLED
    ):
        await async_setup_mcp_server(hass)

    # ── v1.5.1 : LLM API — expose les outils HACA à Mistral/OpenAI/etc. ──
    # L'utilisateur configure : HA Settings → Voice Assistants → [agent] → LLM API → HACA
    if entry.options.get(OPT_LLM_API_ENABLED, DEFAULT_LLM_API_ENABLED):
        try:
            from homeassistant.helpers import llm as _llm
            _llm.async_register_api(hass, HacaLLMAPI(hass))
            _LOGGER.info("[HACA] LLM API 'HACA' enregistrée — configurez-la dans Voice Assistants")
        except Exception as _llm_err:
            _LOGGER.warning("[HACA] Impossible d'enregistrer le LLM API: %s", _llm_err)

    # ── v1.4.0 : Agent IA Proactif (MODULE 16) ───────────────────────────
    if MODULE_16_PROACTIVE_AGENT and entry.options.get(
        OPT_PROACTIVE_AGENT_ENABLED, DEFAULT_PROACTIVE_AGENT_ENABLED
    ):
        async_setup_proactive_agent(hass, entry)

    # ── Post-scan notification listener ──────────────────────────────────
    # Après chaque refresh du coordinator (scan périodique OU déclenché par
    # un événement de modification), compare les issues HIGH avec le scan
    # précédent et envoie une notification persistante pour les nouvelles issues.
    _prev_high_issue_keys: set[str] = set()

    # Le premier scan d'une session se compare à un historique vide : *toutes*
    # les issues présentes y paraissent nouvelles, y compris celles qui
    # existaient déjà avant le redémarrage et les entités que Home Assistant
    # n'a pas fini de restaurer si le plafond de _wait_for_entities_to_settle()
    # a été atteint. Il sert donc de référence, pas d'alerte : on enregistre sa
    # photo, et notification comme Repairs ne parlent qu'à partir du deuxième
    # scan. Le panneau, lui, affiche tout dès le premier.
    _scan_count = 0
    _counted_data: Any = None

    @callback
    def _session_scan_number() -> int:
        """Rang du scan courant dans la session (1 = scan de référence).

        Le compteur avance quand coordinator.data change d'objet — le
        coordinator en construit un neuf à chaque refresh réussi — et non à
        chaque appel : les deux listeners d'un même scan lisent donc la même
        valeur, quel que soit l'ordre dans lequel ils sont appelés. Un refresh
        en échec laisse data inchangé et ne compte pas, sinon un premier scan
        raté consommerait la référence et le suivant alerterait sur tout.
        """
        nonlocal _scan_count, _counted_data
        if coordinator.last_update_success and coordinator.data is not _counted_data:
            _counted_data = coordinator.data
            _scan_count += 1
        return _scan_count

    @callback
    def _on_coordinator_update() -> None:
        """Detect new issues and send persistent notifications based on severity options."""
        nonlocal _prev_high_issue_keys
        cdata = coordinator.data
        if not cdata:
            return

        all_lists = [
            cdata.get("automation_issue_list", []),
            cdata.get("script_issue_list", []),
            cdata.get("entity_issue_list", []),
            cdata.get("performance_issue_list", []),
            cdata.get("security_issue_list", []),
            cdata.get("dashboard_issue_list", []),
            cdata.get("blueprint_issue_list", []),
            cdata.get("scene_issue_list", []),
        ]

        # Check which severity levels should trigger notifications
        opts = entry.options
        notify_high = opts.get("notify_high_severity", True)
        notify_medium = opts.get("notify_medium_severity", False)
        notify_low = opts.get("notify_low_severity", False)
        enabled_severities = set()
        if notify_high:
            enabled_severities.add("high")
        if notify_medium:
            enabled_severities.add("medium")
        if notify_low:
            enabled_severities.add("low")

        if not enabled_severities:
            return

        # Stable identifier for each issue. Dismissed issues are skipped so
        # the post-scan notification never re-surfaces something the user has
        # explicitly chosen to ignore.
        current_issues: dict[str, dict] = {}
        for lst in all_lists:
            for issue in lst:
                if issue.get("ignored"):
                    continue
                sev = issue.get("severity", "low")
                if sev in enabled_severities:
                    key = "|".join([
                        str(issue.get("entity_id", "")),
                        str(issue.get("type", "")),
                        str(issue.get("location", "")),
                    ])
                    current_issues[key] = issue

        if _session_scan_number() <= 1:
            _prev_high_issue_keys = set(current_issues)
            _LOGGER.info(
                "[HACA] First scan of the session: %d issue(s) recorded as the "
                "baseline, no notification — new issues are reported from the "
                "next scan on",
                len(current_issues),
            )
            return

        new_keys = set(current_issues) - _prev_high_issue_keys
        _prev_high_issue_keys = set(current_issues)

        if not new_keys:
            return

        # Build consolidated notification for all new issues
        new_issues = [current_issues[k] for k in new_keys]
        count = len(new_issues)
        score = cdata.get("health_score", "?")

        # Group by source name for readability
        lines: list[str] = []
        for iss in new_issues[:8]:  # cap at 8 to keep notification readable
            name = iss.get("alias") or iss.get("entity_id", "?")
            msg  = (iss.get("message") or "")[:120]
            lines.append(f"- **{name}** : {msg}")
        if count > 8:
            lines.append(_ts(hass, "notifications", "more_issues", count=count - 8))

        body = "\n".join(lines)

        # _ts resolves the language via resolve_notification_language() —
        # i.e. the per-entry notification_language option, then HA system locale.
        title   = _ts(hass, "notifications", "new_issues_title", count=count)
        header  = _ts(hass, "notifications", "new_issues_header", score=score)
        footer  = _ts(hass, "notifications", "new_issues_footer")

        message = header + body + footer

        hass.async_create_task(
            hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "notification_id": f"haca_new_issues_{entry.entry_id}",
                    "title":   title,
                    "message": message,
                },
                blocking=False,
            )
        )
        _LOGGER.info(
            "[HACA] Post-scan notification: %d new issue(s) detected", count
        )

    @callback
    def _on_coordinator_update_repairs() -> None:
        """Sync HIGH issues to HA native Repairs panel after each scan."""
        # Check option dynamically — user can toggle without restart
        if not entry.options.get("repairs_enabled", True):
            return
        if _session_scan_number() <= 1:
            # Scan de référence : on ne touche pas au panneau Réparations, qui
            # garde donc les entrées du dernier scan d'avant le redémarrage
            # jusqu'à ce que le deuxième scan les remplace en bloc.
            _LOGGER.info(
                "[HACA] First scan of the session: Repairs left untouched "
                "(baseline scan) — entries are refreshed at the next scan"
            )
            return
        cdata = coordinator.data
        if cdata:
            hass.async_create_task(async_update_repairs(hass, cdata))

    entry.async_on_unload(
        coordinator.async_add_listener(_on_coordinator_update)
    )
    entry.async_on_unload(
        coordinator.async_add_listener(_on_coordinator_update_repairs)
    )
    # ── End post-scan notification listener ───────────────────────────────

    # Appliquer debug_mode si persisté dans les options
    if entry.options.get("debug_mode", False):
        import logging as _logging
        _logging.getLogger("custom_components.config_auditor").setLevel(_logging.DEBUG)
        _LOGGER.info("[HACA] Debug mode enabled (from saved options)")

    _LOGGER.info("%s v%s setup complete - All 5 modules loaded", NAME, VERSION)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Ne désenregistre PAS le panel ici : cette fonction est appelée à chaque
    reload (save d'options, mise à jour HACS…). Le panel reste affiché dans
    la sidebar pendant le reload et sera ré-enregistré (update=True) dans
    async_setup_entry. async_unregister_panel n'est appelé que dans
    async_remove_entry (désinstallation complète).
    """
    _LOGGER.info("Unloading %s", NAME)

    # Désenregistrer le LLM API HACA
    try:
        from homeassistant.helpers import llm as _llm
        # Prefer the public unregister method if available (HA 2025.x+)
        if hasattr(_llm, "async_unregister_api"):
            _llm.async_unregister_api(hass, HACA_LLM_API_ID)
        else:
            # Fallback for older HA versions: access the internal registry
            # This is a best-effort cleanup — not finding the API is fine.
            _apis = getattr(_llm, "_apis", None) or getattr(_llm, "apis", None)
            if isinstance(_apis, dict):
                _apis.pop(HACA_LLM_API_ID, None)
    except Exception:
        pass

    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}

    # Release the coordinator listener that fires haca_scan_complete.
    _unsub = entry_data.get("_unsub_scan_complete")
    if callable(_unsub):
        try:
            _unsub()
        except Exception:  # noqa: BLE001 — unloading must not fail over this
            pass

    # Stop the in-memory state-change tracker (releases the bus listener).
    tracker = entry_data.get("noisy_tracker")
    if tracker is not None:
        try:
            tracker.stop()
        except Exception:
            pass

    # Flush any delayed .storage write: a reload happening seconds after a scan
    # must not drop the snapshot that is still waiting in the Store delay timer.
    for _key in ("history_manager", "battery_predictor"):
        _component = entry_data.get(_key)
        if _component is not None:
            try:
                await _component.async_flush()
            except Exception as _flush_err:
                _LOGGER.warning("HACA: %s flush failed: %s", _key, _flush_err)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry (appelé manuellement via l'UI HA, pas automatiquement)."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry - Clean Uninstall."""
    _LOGGER.info("Removing %s — clean uninstall", NAME)

    # 0. Ensure panel is unregistered
    await async_unregister_panel(hass)

    # 1. Paths
    reports_path = hass.config.path(REPORTS_DIR)
    backups_path = hass.config.path(BACKUP_DIR)
    # Legacy pre-1.7.6 directories — normally already migrated to .storage
    history_path = Path(hass.config.config_dir) / LEGACY_HISTORY_DIR
    battery_history_path = Path(hass.config.config_dir) / LEGACY_BATTERY_HISTORY_DIR

    # 2. Blocking cleanup — runs in the executor to avoid blocking the event loop
    def _cleanup_files() -> None:
        """Remove all HACA data directories (blocking I/O, runs in executor)."""
        for dir_path in (reports_path, backups_path, history_path, battery_history_path):
            p = Path(dir_path)
            if p.exists() and p.is_dir():
                try:
                    shutil.rmtree(p)
                    _LOGGER.info("Removed directory: %s", p)
                except Exception as e:
                    _LOGGER.error("Failed to remove directory %s: %s", p, e)

    await hass.async_add_executor_job(_cleanup_files)

    # 3. Remove .storage data (audit history + battery snapshots)
    from homeassistant.helpers.storage import Store

    for storage_key in (STORAGE_KEY_HISTORY, STORAGE_KEY_BATTERY_HISTORY):
        try:
            await Store(hass, STORAGE_VERSION, storage_key).async_remove()
            _LOGGER.info("Removed .storage/%s", storage_key)
        except Exception as e:
            _LOGGER.error("Failed to remove .storage/%s: %s", storage_key, e)

    # 4. Persistent notification
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {
            "title": _ts(hass, "notifications", "uninstalled_title", name=NAME),
            "message": _ts(hass, "notifications", "uninstalled_body"),
            "notification_id": "haca_uninstall_notice"
        }
    )
