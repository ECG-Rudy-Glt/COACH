// Pages locales de la coque : assistant de premier lancement, écran Réglages et écran de démarrage.
// La validation de référence et le stockage de la clé sont côté Rust (commande save_settings) ; ici, seulement l'affichage.
// La clé saisie n'est ni mémorisée ici, ni affichée, ni journalisée : elle part dans l'appel save_settings puis le champ est vidé.
(function () {
  "use strict";
  var T = {
    fr: {
      splash: "Démarrage de COACH…", splash_lead: "Le serveur local se lance, quelques secondes au premier démarrage.",
      err_title: "COACH n'a pas pu démarrer", retry: "Réessayer", open_settings: "Ouvrir les réglages",
      welcome: "Bienvenue dans COACH", welcome_lead: "Tout tourne sur cet ordinateur. L'assistant IA est facultatif : COACH construit votre plan et vos objectifs nutritionnels sans lui.",
      settings: "Réglages", settings_lead: "Changer d'assistant IA ou de clé. COACH redémarre son serveur local ; vos données sont conservées.",
      provider: "Assistant IA", p_none: "Aucun : désactiver l'IA", p_ollama: "Ollama (local, sans clé)",
      key: "Clé d'API", key_help: "Rangée dans le trousseau de votre système, jamais dans un fichier. Elle ne s'affiche plus ensuite.",
      key_stored: "Une clé est déjà enregistrée. Laissez vide pour la garder, ou saisissez-en une nouvelle.",
      get_key: "Créer une clé chez ce fournisseur", clear_key: "Supprimer la clé enregistrée",
      url: "Adresse du serveur Ollama", url_help: "Laissez la valeur par défaut si Ollama tourne sur cet ordinateur. Installez Ollama puis téléchargez un modèle, comme indiqué dans le guide.",
      model: "Modèle (facultatif)", model_help: "Vide = modèle conseillé par COACH pour ce fournisseur.",
      budget: "Budget mensuel d'IA (€)", budget_help: "COACH arrête d'appeler l'IA quand ce budget est atteint dans le mois. Fixez aussi un plafond chez le fournisseur (voir le guide).",
      start: "Démarrer COACH", save: "Enregistrer et redémarrer", cancel: "Annuler",
      other: "English", saving: "Enregistrement…", starting: "Démarrage du serveur local…", need_key: "Saisissez la clé d'API de ce fournisseur, ou choisissez « Aucun ».",
      notify: "Rappels par ntfy ou e-mail (facultatif)", notify_help: "Le serveur de COACH peut envoyer des rappels et un résumé hebdomadaire. Laissez vide pour ne rien activer. Les mots de passe et jetons vont dans le trousseau du système.",
      ntfy_url: "Adresse du serveur ntfy", ntfy_public: "Adresse ntfy saisie dans l'application du téléphone (si différente)", ntfy_token: "Jeton d'accès ntfy (nécessaire : COACH n'envoie sur ntfy qu'avec un jeton)",
      secret_stored: "Déjà enregistré. Laissez vide pour le garder.", smtp_host: "Serveur SMTP (nom seul)", smtp_port: "Port SMTP", smtp_user: "Utilisateur SMTP", smtp_password: "Mot de passe SMTP",
      smtp_from: "Adresse d'expédition (vide = l'utilisateur SMTP)", notify_auto: "Envoyer automatiquement les rappels et le résumé hebdomadaire", notify_hour: "Heure d'envoi (0 à 23, heure de cet ordinateur)",
      clear_secrets: "Supprimer le jeton ntfy et le mot de passe SMTP enregistrés", notify_after: "Ensuite, chaque personne choisit son sujet ntfy ou active l'e-mail dans Profil, Notifications. Les notifications push du navigateur ne sont pas disponibles dans l'application de bureau.",
      secrets_cleared: "Jeton et mot de passe supprimés à l'enregistrement.",
      data_hint: "Vos données : ", key_cleared: "Clé supprimée. Choisissez « Aucun » ou saisissez une nouvelle clé."
    },
    en: {
      splash: "Starting COACH…", splash_lead: "The local server is starting, a few seconds on first launch.",
      err_title: "COACH could not start", retry: "Retry", open_settings: "Open settings",
      welcome: "Welcome to COACH", welcome_lead: "Everything runs on this computer. The AI assistant is optional: COACH builds your plan and nutrition targets without it.",
      settings: "Settings", settings_lead: "Change AI assistant or key. COACH restarts its local server; your data is kept.",
      provider: "AI assistant", p_none: "None: turn AI off", p_ollama: "Ollama (local, no key)",
      key: "API key", key_help: "Stored in your system keychain, never in a file. It is not shown again.",
      key_stored: "A key is already stored. Leave empty to keep it, or enter a new one.",
      get_key: "Create a key with this provider", clear_key: "Delete the stored key",
      url: "Ollama server address", url_help: "Keep the default if Ollama runs on this computer. Install Ollama and download a model, as explained in the guide.",
      model: "Model (optional)", model_help: "Empty = the model COACH recommends for this provider.",
      budget: "Monthly AI budget (€)", budget_help: "COACH stops calling the AI once this budget is reached in the month. Also set a spending cap with your provider (see the guide).",
      start: "Start COACH", save: "Save and restart", cancel: "Cancel",
      other: "Français", saving: "Saving…", starting: "Starting the local server…", need_key: "Enter this provider's API key, or choose “None”.",
      notify: "Reminders by ntfy or e-mail (optional)", notify_help: "The COACH server can send reminders and a weekly digest. Leave empty to enable nothing. Passwords and tokens go to the system keychain.",
      ntfy_url: "ntfy server address", ntfy_public: "ntfy address typed in the phone app (if different)", ntfy_token: "ntfy access token (required: COACH only sends to ntfy with a token)",
      secret_stored: "Already stored. Leave empty to keep it.", smtp_host: "SMTP server (name only)", smtp_port: "SMTP port", smtp_user: "SMTP user", smtp_password: "SMTP password",
      smtp_from: "Sender address (empty = the SMTP user)", notify_auto: "Send reminders and the weekly digest automatically", notify_hour: "Send hour (0 to 23, this computer's time)",
      clear_secrets: "Delete the stored ntfy token and SMTP password", notify_after: "Then each person picks their ntfy topic or turns e-mail on in Profile, Notifications. Browser push notifications are not available in the desktop app.",
      secrets_cleared: "Token and password deleted when you save.",
      data_hint: "Your data: ", key_cleared: "Key deleted. Choose “None” or enter a new key."
    }
  };
  // Pages de création de clé (liste blanche côté Rust) et modèles conseillés (data/llm_providers.yaml).
  var KEY_PAGES = {
    anthropic: "https://console.anthropic.com/settings/keys", openai: "https://platform.openai.com/api-keys",
    gemini: "https://aistudio.google.com/apikey", mistral: "https://console.mistral.ai/api-keys",
    openrouter: "https://openrouter.ai/keys", ollama: "https://ollama.com/download"
  };
  var MODELS = { anthropic: "claude-sonnet-5-5", openai: "gpt-4o", gemini: "gemini-3.8-flash", mistral: "mistral-large-latest", openrouter: "openrouter/auto", ollama: "qwen2.5:7b" };

  var lang = "fr";
  try { lang = localStorage.getItem("lang") || (navigator.language || "fr").slice(0, 2); } catch (e) { lang = (navigator.language || "fr").slice(0, 2); }
  if (!T[lang]) lang = "en";

  var $ = function (id) { return document.getElementById(id); };
  var state = null, editing = false, keyCleared = false, hadKey = false, secretsCleared = false;

  function tr(k) { return T[lang][k]; }
  function apply() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach(function (el) { el.textContent = tr(el.getAttribute("data-i18n")); });
    $("lang").textContent = tr("other");
    if (editing) { $("form-title").textContent = tr("settings"); $("form-lead").textContent = tr("settings_lead"); $("go").textContent = tr("save"); }
    if (state && state.data_dir) { $("data-hint").textContent = tr("data_hint") + state.data_dir; }
  }
  function show(id) {
    ["view-splash", "view-error", "view-form"].forEach(function (v) { $(v).hidden = v !== id; });
  }
  function say(text, cls) { var m = $("msg"); m.textContent = text || ""; m.className = "msg" + (cls ? " " + cls : ""); }
  function invoke(cmd, args) {
    var t = window.__TAURI__ && window.__TAURI__.core;
    return t ? t.invoke(cmd, args) : Promise.reject("Tauri indisponible");
  }

  function refreshFields() {
    var p = $("provider").value, ai = p !== "none";
    $("ai-fields").hidden = !ai;
    $("key-block").hidden = !ai || p === "ollama";
    $("url-block").hidden = p !== "ollama";
    $("model").placeholder = MODELS[p] || "";
    $("get-key").hidden = !KEY_PAGES[p];
    $("get-key").textContent = p === "ollama" ? (lang === "fr" ? "Télécharger Ollama" : "Download Ollama") : tr("get_key");
    if (ai && p !== "ollama") {
      invoke("has_key", { provider: p }).then(function (has) {
        hadKey = has && !keyCleared;
        $("key-stored").hidden = !hadKey; $("clear-key").hidden = !hadKey;
      }).catch(function () { hadKey = false; });
    }
  }

  function showForm() {
    show("view-form");
    var s = state.settings;
    if (s) {
      $("provider").value = s.provider; $("model").value = s.model || ""; $("base-url").value = s.base_url || ""; $("budget").value = String(s.budget);
    }
    var n = (s && s.notify) || {};
    $("ntfy-url").value = n.ntfy_url || ""; $("ntfy-public-url").value = n.ntfy_public_url || ""; $("smtp-host").value = n.smtp_host || "";
    $("smtp-port").value = n.smtp_port || ""; $("smtp-user").value = n.smtp_user || ""; $("smtp-from").value = n.smtp_from || "";
    $("notify-auto").checked = !!n.auto; $("notify-hour").value = n.hour || "";
    $("ntfy-stored").hidden = !state.has_ntfy_token; $("smtp-stored").hidden = !state.has_smtp_password;
    $("clear-secrets").hidden = !(state.has_ntfy_token || state.has_smtp_password);
    $("notify-block").open = !!(n.ntfy_url || n.smtp_host);
    $("cancel").hidden = !(editing && state.running);
    apply(); refreshFields();
  }

  function launch(restart) {
    show("view-splash"); apply();
    invoke("start_app", { restart: !!restart }).catch(function (e) {
      $("error-text").textContent = String(e);
      show("view-error");
    });
  }

  $("lang").addEventListener("click", function () {
    lang = lang === "fr" ? "en" : "fr";
    try { localStorage.setItem("lang", lang); } catch (e) { /* sans stockage : tant pis */ }
    apply(); refreshFields(); say("");
  });
  $("provider").addEventListener("change", function () { keyCleared = false; say(""); refreshFields(); });
  $("get-key").addEventListener("click", function () {
    var url = KEY_PAGES[$("provider").value];
    if (url) { invoke("open_external", { url: url }).catch(function (e) { say(String(e), "err"); }); }
  });
  $("clear-key").addEventListener("click", function () {
    keyCleared = true; hadKey = false; $("key-stored").hidden = true; $("clear-key").hidden = true; say(tr("key_cleared"), "ok");
  });
  $("clear-secrets").addEventListener("click", function () {
    secretsCleared = true; $("ntfy-stored").hidden = true; $("smtp-stored").hidden = true; $("clear-secrets").hidden = true; say(tr("secrets_cleared"), "ok");
  });
  $("cancel").addEventListener("click", function () { launch(false); });
  $("retry").addEventListener("click", function () { launch(true); });
  $("to-settings").addEventListener("click", function () { editing = true; showForm(); });

  $("form").addEventListener("submit", function (ev) {
    ev.preventDefault();
    var p = $("provider").value, keyField = $("api-key"), key = keyField.value;
    if (p !== "none" && p !== "ollama" && !key.trim() && !hadKey) { say(tr("need_key"), "err"); return; }
    $("go").disabled = true; say(tr("saving"));
    invoke("save_settings", {
      input: {
        provider: p, api_key: key, clear_key: keyCleared && !key.trim(), model: $("model").value, base_url: p === "ollama" ? $("base-url").value : "",
        budget: parseFloat($("budget").value.replace(",", ".")) || 0,
        notify: {
          ntfy_url: $("ntfy-url").value, ntfy_public_url: $("ntfy-public-url").value, smtp_host: $("smtp-host").value, smtp_port: $("smtp-port").value,
          smtp_user: $("smtp-user").value, smtp_from: $("smtp-from").value, auto: $("notify-auto").checked, hour: $("notify-hour").value
        },
        ntfy_token: $("ntfy-token").value, clear_ntfy_token: secretsCleared && !$("ntfy-token").value.trim(),
        smtp_password: $("smtp-password").value, clear_smtp_password: secretsCleared && !$("smtp-password").value.trim()
      }
    }).then(function () {
      $("ntfy-token").value = ""; $("smtp-password").value = ""; secretsCleared = false;
      keyField.value = ""; // la clé est dans le trousseau : on ne la garde pas dans la page
      say(tr("starting"), "ok");
      launch(true);
    }).catch(function (e) { say(String(e), "err"); }).then(function () { $("go").disabled = false; });
  });

  apply();
  invoke("get_state").then(function (s) {
    state = s;
    editing = new URLSearchParams(window.location.search).get("settings") === "1";
    if (!s.configured) { editing = false; showForm(); }
    else if (editing) { showForm(); }
    else { launch(false); }
  }).catch(function (e) { $("error-text").textContent = String(e); show("view-error"); });
})();
