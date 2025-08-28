import os
import asyncio
import re
import json
import zipfile
import tempfile
import shutil
import logging
import sys
from datetime import datetime
from telethon import TelegramClient, events
from telethon.events import ChatAction
from dotenv import load_dotenv
from predictor import CardPredictor
from scheduler import PredictionScheduler
from yaml_manager import init_database, db
from aiohttp import web
import threading

# Configuration du logging détaillé pour Render.com
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('render_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
try:
    API_ID = int(os.getenv('API_ID') or '0')
    API_HASH = os.getenv('API_HASH') or ''
    BOT_TOKEN = os.getenv('BOT_TOKEN') or ''
    ADMIN_ID = int(os.getenv('ADMIN_ID') or '0')
    PORT = int(os.getenv('PORT') or '10000')

    # Validation des variables requises
    if not API_ID or API_ID == 0:
        raise ValueError("API_ID manquant ou invalide")
    if not API_HASH:
        raise ValueError("API_HASH manquant")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN manquant")

    print(f"✅ Configuration chargée: API_ID={API_ID}, ADMIN_ID={ADMIN_ID}, PORT={PORT}")
except Exception as e:
    print(f"❌ Erreur configuration: {e}")
    print("Vérifiez vos variables d'environnement")
    exit(1)

# Fichier de configuration persistante
CONFIG_FILE = 'bot_config.json'

# Variables d'état
detected_stat_channel = None
detected_display_channel = None
confirmation_pending = {}
prediction_interval = 1  # Intervalle en minutes avant de chercher "A" (défaut: 1 min - RAPIDE)
cooldown_interval = 5   # Intervalle en secondes avant re-vérification des règles (défaut: 5 sec - TRÈS RAPIDE)
last_rule_check = None  # Timestamp de la dernière vérification des règles

def load_config():
    """Load configuration with priority: JSON > Database"""
    global detected_stat_channel, detected_display_channel, prediction_interval, cooldown_interval
    try:
        # Toujours essayer JSON en premier (source de vérité)
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                detected_stat_channel = config.get('stat_channel')
                detected_display_channel = config.get('display_channel')
                prediction_interval = config.get('prediction_interval', 5)
                cooldown_interval = config.get('cooldown_interval', 30)
                print(f"✅ Configuration chargée depuis JSON: Stats={detected_stat_channel}, Display={detected_display_channel}, Intervalle={prediction_interval}min, Cooldown={cooldown_interval}sec")
                return

        # Fallback sur base de données si JSON n'existe pas
        if db:
            detected_stat_channel = db.get_config('stat_channel')
            detected_display_channel = db.get_config('display_channel')
            interval_config = db.get_config('prediction_interval')
            cooldown_config = db.get_config('cooldown_interval')
            if detected_stat_channel:
                detected_stat_channel = int(detected_stat_channel)
            if detected_display_channel:
                detected_display_channel = int(detected_display_channel)
            if interval_config:
                prediction_interval = int(interval_config)
            if cooldown_config:
                cooldown_interval = int(cooldown_config)
            print(f"✅ Configuration chargée depuis la DB: Stats={detected_stat_channel}, Display={detected_display_channel}, Intervalle={prediction_interval}min, Cooldown={cooldown_interval}sec")
        else:
            print("ℹ️ Aucune configuration trouvée, nouvelle configuration")
    except Exception as e:
        print(f"⚠️ Erreur chargement configuration: {e}")
        # Valeurs par défaut en cas d'erreur
        detected_stat_channel = None
        detected_display_channel = None
        prediction_interval = 5
        cooldown_interval = 30

def save_config():
    """Save configuration to database and JSON backup"""
    try:
        if db:
            # Sauvegarde en base de données
            db.set_config('stat_channel', detected_stat_channel)
            db.set_config('display_channel', detected_display_channel)
            db.set_config('prediction_interval', prediction_interval)
            db.set_config('cooldown_interval', cooldown_interval)
            print("💾 Configuration sauvegardée en base de données")

        # Sauvegarde JSON de secours
        config = {
            'stat_channel': detected_stat_channel,
            'display_channel': detected_display_channel,
            'prediction_interval': prediction_interval,
            'cooldown_interval': cooldown_interval
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        print(f"💾 Configuration sauvegardée: Stats={detected_stat_channel}, Display={detected_display_channel}, Intervalle={prediction_interval}min, Cooldown={cooldown_interval}sec")
    except Exception as e:
        print(f"❌ Erreur sauvegarde configuration: {e}")

def update_channel_config(source_id: int, target_id: int):
    """Update channel configuration"""
    global detected_stat_channel, detected_display_channel
    detected_stat_channel = source_id
    detected_display_channel = target_id
    save_config()

# Initialize database
database = init_database()

# Gestionnaire de prédictions (sera mis à jour avec yaml_manager après initialisation)
predictor = CardPredictor()

# Planificateur automatique
scheduler = None

# Initialize Telegram client with unique session name
import time
session_name = f'bot_session_{int(time.time())}'
client = TelegramClient(session_name, API_ID, API_HASH)

async def start_bot():
    """Start the bot with proper error handling"""
    try:
        logger.info("🚀 DÉMARRAGE DU BOT - Configuration en cours...")

        # Load saved configuration first
        load_config()
        logger.info(f"✅ Configuration chargée - Cooldown: {cooldown_interval}s, Intervalle: {prediction_interval}min")

        # Connecter le yaml_manager au predictor
        predictor.set_yaml_manager(database)
        logger.info("🔗 Predictor connecté au gestionnaire YAML")

        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Bot Telegram connecté avec succès")

        # Auto-démarrage du scheduler si les canaux sont configurés
        global scheduler
        if detected_stat_channel and detected_display_channel and not scheduler:
            scheduler = PredictionScheduler(
                client, predictor,
                detected_stat_channel, detected_display_channel
            )
            # Démarre le planificateur en arrière-plan
            asyncio.create_task(scheduler.run_scheduler())
            logger.info("🤖 Planificateur automatique démarré au lancement du bot")
            logger.info(f"📊 Surveillance ACTIVE: Canal {detected_stat_channel} → Canal {detected_display_channel}")
        else:
            logger.warning("⚠️ Scheduler non démarré - canaux non configurés ou déjà actif")

        # Get bot info
        me = await client.get_me()
        username = getattr(me, 'username', 'Unknown') or f"ID:{getattr(me, 'id', 'Unknown')}"
        logger.info(f"✅ Bot opérationnel: @{username}")

    except Exception as e:
        logger.error(f"❌ Erreur critique lors du démarrage: {e}")
        return False

    return True

# --- INVITATION / CONFIRMATION ---
@client.on(events.ChatAction())
async def handler_join(event):
    """Handle bot joining channels/groups"""
    global confirmation_pending

    try:
        print(f"ChatAction event: {event}")
        print(f"user_joined: {event.user_joined}, user_added: {event.user_added}")
        print(f"user_id: {event.user_id}, chat_id: {event.chat_id}")

        if event.user_joined or event.user_added:
            me = await client.get_me()
            me_id = getattr(me, 'id', None)
            print(f"Mon ID: {me_id}, Event user_id: {event.user_id}")

            if event.user_id == me_id:
                # Normaliser l'ID du canal pour corriger les problèmes d'affichage
                channel_id = event.chat_id
                original_id = channel_id

                # Correction pour les IDs de supergroups/channels mal formatés
                if str(channel_id).startswith('-207') and len(str(channel_id)) == 14:
                    # Convertir -207XXXXXXXXX vers -100XXXXXXXXX
                    channel_id = int('-100' + str(channel_id)[4:])
                    print(f"🔧 ID canal corrigé: {original_id} → {channel_id}")

                # Éviter les doublons : vérifier si ce canal (normalisé) est déjà en attente
                if channel_id in confirmation_pending:
                    print(f"⚠️ Canal {channel_id} déjà en attente de configuration, événement {original_id} ignoré")
                    return

                confirmation_pending[channel_id] = 'waiting_confirmation'

                # Get channel info
                try:
                    chat = await client.get_entity(channel_id)
                    chat_title = getattr(chat, 'title', f'Canal {channel_id}')
                except:
                    chat_title = f'Canal {channel_id}'

                # Send private invitation to admin
                invitation_msg = f"""🔔 **Nouveau canal détecté**

📋 **Canal** : {chat_title}
🆔 **ID** : {channel_id}

**Choisissez le type de canal** :
• `/set_stat {channel_id}` - Canal de statistiques
• `/set_display {channel_id}` - Canal de diffusion

Envoyez votre choix en réponse à ce message."""

                try:
                    await client.send_message(ADMIN_ID, invitation_msg)
                    print(f"Invitation envoyée à l'admin pour le canal: {chat_title} ({event.chat_id})")
                except Exception as e:
                    print(f"Erreur envoi invitation privée: {e}")
                    # Fallback: send to the channel temporarily for testing
                    await client.send_message(event.chat_id, f"⚠️ Impossible d'envoyer l'invitation privée. Canal ID: {event.chat_id}")
                    print(f"Message fallback envoyé dans le canal {event.chat_id}")
    except Exception as e:
        print(f"Erreur dans handler_join: {e}")

@client.on(events.NewMessage(pattern=r'/set_stat (-?\d+)'))
async def set_stat_channel(event):
    """Set statistics channel (only admin in private)"""
    global detected_stat_channel, confirmation_pending

    try:
        # Only allow in private chat with admin
        if event.is_group or event.is_channel:
            return

        if event.sender_id != ADMIN_ID:
            await event.respond("❌ Seul l'administrateur peut configurer les canaux")
            return

        # Extract channel ID from command
        match = event.pattern_match
        channel_id = int(match.group(1))

        # Check if channel is waiting for confirmation
        if channel_id not in confirmation_pending:
            await event.respond("❌ Ce canal n'est pas en attente de configuration")
            return

        detected_stat_channel = channel_id
        confirmation_pending[channel_id] = 'configured_stat'

        # Save configuration
        save_config()

        try:
            chat = await client.get_entity(channel_id)
            chat_title = getattr(chat, 'title', f'Canal {channel_id}')
        except:
            chat_title = f'Canal {channel_id}'

        await event.respond(f"✅ **Canal de statistiques configuré**\n📋 {chat_title}\n\n✨ Le bot surveillera ce canal pour les prédictions - développé par Sossou Kouamé Appolinaire\n💾 Configuration sauvegardée automatiquement")
        print(f"Canal de statistiques configuré: {channel_id}")

    except Exception as e:
        print(f"Erreur dans set_stat_channel: {e}")

@client.on(events.NewMessage(pattern=r'/set_display (-?\d+)'))
async def set_display_channel(event):
    """Set display channel (only admin in private)"""
    global detected_display_channel, confirmation_pending

    try:
        # Only allow in private chat with admin
        if event.is_group or event.is_channel:
            return

        if event.sender_id != ADMIN_ID:
            await event.respond("❌ Seul l'administrateur peut configurer les canaux")
            return

        # Extract channel ID from command
        match = event.pattern_match
        channel_id = int(match.group(1))

        # Check if channel is waiting for confirmation
        if channel_id not in confirmation_pending:
            await event.respond("❌ Ce canal n'est pas en attente de configuration")
            return

        detected_display_channel = channel_id
        confirmation_pending[channel_id] = 'configured_display'

        # Save configuration
        save_config()

        try:
            chat = await client.get_entity(channel_id)
            chat_title = getattr(chat, 'title', f'Canal {channel_id}')
        except:
            chat_title = f'Canal {channel_id}'

        await event.respond(f"✅ **Canal de diffusion configuré**\n📋 {chat_title}\n\n🚀 Le bot publiera les prédictions dans ce canal - développé par Sossou Kouamé Appolinaire\n💾 Configuration sauvegardée automatiquement")
        print(f"Canal de diffusion configuré: {channel_id}")

    except Exception as e:
        print(f"Erreur dans set_display_channel: {e}")

# --- COMMANDES DE BASE ---
@client.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Send welcome message when user starts the bot"""
    try:
        welcome_msg = """🎯 **Bot de Prédiction de Cartes - Bienvenue !**

🔹 **Développé par Sossou Kouamé Appolinaire**

**Fonctionnalités** :
• Prédictions automatiques anticipées (déclenchées sur As dans premier groupe)
• Prédictions pour les prochains jeux
• Vérification des résultats avec statuts détaillés (✅0️⃣, ✅1️⃣, ✅2️⃣, ✅3️⃣, ❌)

**Configuration** :
1. Ajoutez-moi dans vos canaux
2. Je vous enverrai automatiquement une invitation privée
3. Répondez avec `/set_stat [ID]` ou `/set_display [ID]`

**Commandes** :
• `/start` - Ce message
• `/status` - État du bot (admin)
• `/intervalle` - Configure le délai de prédiction (admin)
• `/sta` - Statut des déclencheurs (admin)
• `/reset` - Réinitialiser (admin)
• `/deploy` - Pack de déploiement (admin)

Le bot est prêt à analyser vos jeux ! 🚀"""

        await event.respond(welcome_msg)
        print(f"Message de bienvenue envoyé à l'utilisateur {event.sender_id}")

        # Test message private pour vérifier la connectivité
        if event.sender_id == ADMIN_ID:
            await asyncio.sleep(2)
            test_msg = "🔧 Test de connectivité : Je peux vous envoyer des messages privés !"
            await event.respond(test_msg)

    except Exception as e:
        print(f"Erreur dans start_command: {e}")

# --- COMMANDES ADMINISTRATIVES ---
@client.on(events.NewMessage(pattern='/status'))
async def show_status(event):
    """Show bot status (admin only)"""
    try:
        if event.sender_id != ADMIN_ID:
            return

        config_status = "✅ Sauvegardée" if os.path.exists(CONFIG_FILE) else "❌ Non sauvegardée"
        status_msg = f"""📊 **Statut du Bot**

Canal statistiques: {'✅ Configuré' if detected_stat_channel else '❌ Non configuré'} ({detected_stat_channel})
Canal diffusion: {'✅ Configuré' if detected_display_channel else '❌ Non configuré'} ({detected_display_channel})
⏱️ Intervalle de prédiction: {prediction_interval} minutes
⏳ Cooldown de vérification: {cooldown_interval} secondes
Configuration persistante: {config_status}
Prédictions actives: {len(predictor.prediction_status)}
Dernières prédictions: {len(predictor.last_predictions)}
"""
        await event.respond(status_msg)
    except Exception as e:
        print(f"Erreur dans show_status: {e}")

@client.on(events.NewMessage(pattern='/reset'))
async def reset_data(event):
    """Réinitialisation des données (admin uniquement)"""
    try:
        if event.sender_id != ADMIN_ID:
            return

        # Réinitialiser les prédictions en attente
        pending_predictions.clear()

        # Réinitialiser les données YAML
        await yaml_manager.reset_all_data()

        msg = """🔄 **Données réinitialisées avec succès !**

✅ Prédictions en attente: vidées
✅ Base de données YAML: réinitialisée
✅ Configuration: préservée

Le bot est prêt pour un nouveau cycle."""

        await event.respond(msg)
        print(f"Données réinitialisées par l'admin")

    except Exception as e:
        print(f"Erreur dans reset_data: {e}")
        await event.respond(f"❌ Erreur lors de la réinitialisation: {e}")

@client.on(events.NewMessage(pattern='/ni'))
async def ni_command(event):
    """Commande /ni - Informations sur le système de prédiction"""
    try:
        # Utiliser les variables globales configurées
        stats_channel = detected_stat_channel or 'Non configuré'
        display_channel = detected_display_channel or 'Non configuré'

        # Compter les prédictions actives depuis le predictor
        active_predictions = len([s for s in predictor.prediction_status.values() if s == '⌛'])

        msg = f"""🎯 **Système de Prédiction NI - Statut**

📊 **Configuration actuelle**:
• Canal source: {stats_channel}
• Canal affichage: {display_channel}
• Prédictions actives: {active_predictions}
• Intervalle: {prediction_interval} minute(s)
• Cooldown: {cooldown_interval} seconde(s)

🎮 **Fonctionnalités**:
• Déclenchement automatique sur As (A) dans premier groupe
• Vérification séquentielle avec offsets 0→1→2→3
• Format: "🔵XXX 🔵3K: statut :⏳"

🔧 **Commandes disponibles**:
• `/set_stat [ID]` - Configurer canal source
• `/set_display [ID]` - Configurer canal affichage
• `/status` - Statut détaillé du bot
• `/reset` - Réinitialiser les données
• `/intervalle [min]` - Configurer délai
• `/cooldown [sec]` - Configurer cooldown

✅ **Bot opérationnel** - Version 2025"""

        await event.respond(msg)
        print(f"Commande /ni exécutée par {event.sender_id}")

    except Exception as e:
        print(f"Erreur dans ni_command: {e}")
        await event.respond(f"❌ Erreur: {e}")


@client.on(events.NewMessage(pattern='/test_invite'))
async def test_invite(event):
    """Test sending invitation (admin only)"""
    try:
        if event.sender_id != ADMIN_ID:
            return

        # Test invitation message
        test_msg = f"""🔔 **Test d'invitation**

📋 **Canal test** : Canal de test
🆔 **ID** : -1001234567890

**Choisissez le type de canal** :
• `/set_stat -1001234567890` - Canal de statistiques
• `/set_display -1001234567890` - Canal de diffusion

Ceci est un message de test pour vérifier les invitations."""

        await event.respond(test_msg)
        print(f"Message de test envoyé à l'admin")

    except Exception as e:
        print(f"Erreur dans test_invite: {e}")

@client.on(events.NewMessage(pattern='/sta'))
async def show_trigger_numbers(event):
    """Show current trigger numbers for automatic predictions"""
    try:
        if event.sender_id != ADMIN_ID:
            return

        # Plus de trigger_numbers, nouveau système basé sur les J
        trigger_nums = ["UN SEUL J dans 2ème groupe"]

        # Recharger la configuration pour éviter les valeurs obsolètes
        load_config()

        msg = f"""📊 **Statut des Déclencheurs Automatiques**

🎯 **Numéros déclencheurs**: {', '.join(map(str, trigger_nums))}

📋 **Fonctionnement**:
• Le bot surveille les jeux avec numéros {', '.join(map(str, trigger_nums))}
• Il prédit automatiquement le prochain jeu
• Format: "🔵XXX 🔵3K: statut :⏳"

📈 **Statistiques actuelles**:
• Prédictions actives: {len([s for s in predictor.prediction_status.values() if s == '⌛'])}
• Canal stats configuré: {'✅' if detected_stat_channel else '❌'} ({detected_stat_channel or 'Aucun'})
• Canal affichage configuré: {'✅' if detected_display_channel else '❌'} ({detected_display_channel or 'Aucun'})

🔧 **Configuration actuelle**:
• Stats: {detected_stat_channel if detected_stat_channel else 'Non configuré'}
• Display: {detected_display_channel if detected_display_channel else 'Non configuré'}
• Cooldown: {cooldown_interval} secondes"""

        await event.respond(msg)
        print(f"Statut des déclencheurs envoyé à l'admin")

    except Exception as e:
        print(f"Erreur dans show_trigger_numbers: {e}")
        await event.respond(f"❌ Erreur: {e}")

# Commande /report supprimée selon demande utilisateur

# Handler /deploy supprimé - remplacé par le handler 2D unique

@client.on(events.NewMessage(pattern='/auto'))
async def quick_scheduler_start(event):
    """Démarrage rapide du scheduler (admin uniquement)"""
    global scheduler
    try:
        if event.sender_id != ADMIN_ID:
            return

        if detected_stat_channel and detected_display_channel:
            if not scheduler or not scheduler.is_running:
                scheduler = PredictionScheduler(
                    client, predictor,
                    detected_stat_channel, detected_display_channel
                )
                # Démarre le planificateur en arrière-plan
                asyncio.create_task(scheduler.run_scheduler())

                await event.respond(f"""🚀 **SCHEDULER DÉMARRÉ!**

📊 Configuration active:
• Canal source: {detected_stat_channel}
• Canal cible: {detected_display_channel}
• Status: 🟢 ACTIF

🤖 Le bot génère maintenant des prédictions automatiques!""")

                print(f"✅ Scheduler forcé par commande /auto")
            else:
                await event.respond("⚠️ Scheduler déjà actif!")
        else:
            await event.respond("❌ Canaux non configurés. Utilisez /set_stat et /set_display d'abord.")

    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")

@client.on(events.NewMessage(pattern='/scheduler'))
async def manage_scheduler(event):
    """Gestion du planificateur automatique (admin uniquement)"""
    global scheduler
    try:
        if event.sender_id != ADMIN_ID:
            return

        # Parse command arguments
        message_parts = event.message.message.split()
        if len(message_parts) < 2:
            await event.respond("""🤖 **Commandes du Planificateur Automatique**

**Usage**: `/scheduler [commande]`

**Commandes disponibles**:
• `start` - Démarre le planificateur automatique
• `stop` - Arrête le planificateur
• `status` - Affiche le statut actuel
• `generate` - Génère une nouvelle planification
• `config [source_id] [target_id]` - Configure les canaux

**Exemple**: `/scheduler config -1001234567890 -1001987654321`""")
            return

        command = message_parts[1].lower()

        if command == "start":
            if not scheduler:
                if detected_stat_channel and detected_display_channel:
                    scheduler = PredictionScheduler(
                        client, predictor,
                        detected_stat_channel, detected_display_channel
                    )
                    # Démarre le planificateur en arrière-plan
                    asyncio.create_task(scheduler.run_scheduler())
                    await event.respond("✅ **Planificateur démarré**\n\nLe système de prédictions automatiques est maintenant actif.")
                else:
                    await event.respond("❌ **Configuration manquante**\n\nVeuillez d'abord configurer les canaux source et cible avec `/set_stat` et `/set_display`.")
            else:
                await event.respond("⚠️ **Planificateur déjà actif**\n\nUtilisez `/scheduler stop` pour l'arrêter.")

        elif command == "stop":
            if scheduler:
                scheduler.stop_scheduler()
                scheduler = None
                await event.respond("🛑 **Planificateur arrêté**\n\nLes prédictions automatiques sont désactivées.")
            else:
                await event.respond("ℹ️ **Planificateur non actif**\n\nUtilisez `/scheduler start` pour le démarrer.")

        elif command == "status":
            if scheduler:
                status = scheduler.get_schedule_status()
                status_msg = f"""📊 **Statut du Planificateur**

🔄 **État**: {'🟢 Actif' if status['is_running'] else '🔴 Inactif'}
📋 **Planification**:
• Total de prédictions: {status['total']}
• Prédictions lancées: {status['launched']}
• Prédictions vérifiées: {status['verified']}
• En attente: {status['pending']}

⏰ **Prochaine prédiction**: {status['next_launch'] or 'Aucune'}

🔧 **Configuration**:
• Canal source: {detected_stat_channel}
• Canal cible: {detected_display_channel}"""
                await event.respond(status_msg)
            else:
                await event.respond("ℹ️ **Planificateur non configuré**\n\nUtilisez `/scheduler start` pour l'activer.")

        elif command == "generate":
            if scheduler:
                scheduler.regenerate_schedule()
                await event.respond("🔄 **Nouvelle planification générée**\n\nLa planification quotidienne a été régénérée avec succès.")
            else:
                # Crée un planificateur temporaire pour générer
                temp_scheduler = PredictionScheduler(client, predictor, 0, 0)
                temp_scheduler.regenerate_schedule()
                await event.respond("✅ **Planification générée**\n\nFichier `prediction.yaml` créé. Utilisez `/scheduler start` pour activer.")

        elif command == "config" and len(message_parts) >= 4:
            source_id = int(message_parts[2])
            target_id = int(message_parts[3])

            # Met à jour la configuration globale
            update_channel_config(source_id, target_id)

            await event.respond(f"""✅ **Configuration mise à jour**

📥 **Canal source**: {source_id}
📤 **Canal cible**: {target_id}

Utilisez `/scheduler start` pour activer le planificateur.""")

        else:
            await event.respond("❌ **Commande inconnue**\n\nUtilisez `/scheduler` sans paramètre pour voir l'aide.")

    except Exception as e:
        print(f"Erreur dans manage_scheduler: {e}")
        await event.respond(f"❌ Erreur: {e}")

@client.on(events.NewMessage(pattern='/schedule_info'))
async def schedule_info(event):
    """Affiche les informations détaillées de la planification (admin uniquement)"""
    try:
        if event.sender_id != ADMIN_ID:
            return

        if scheduler and scheduler.schedule_data:
            # Affiche les 10 prochaines prédictions
            current_time = scheduler.get_current_time_slot()
            upcoming = []

            for numero, data in scheduler.schedule_data.items():
                if (not data["launched"] and
                    data["heure_lancement"] >= current_time):
                    upcoming.append((numero, data["heure_lancement"]))

            upcoming.sort(key=lambda x: x[1])
            upcoming = upcoming[:10]  # Limite à 10

            msg = "📅 **Prochaines Prédictions Automatiques**\n\n"
            for numero, heure in upcoming:
                msg += f"🔵 {numero} → {heure}\n"

            if not upcoming:
                msg += "ℹ️ Aucune prédiction en attente pour aujourd'hui."

            await event.respond(msg)
        else:
            await event.respond("❌ **Aucune planification active**\n\nUtilisez `/scheduler generate` pour créer une planification.")

    except Exception as e:
        print(f"Erreur dans schedule_info: {e}")
        await event.respond(f"❌ Erreur: {e}")

@client.on(events.NewMessage(pattern='/intervalle'))
async def set_prediction_interval(event):
    """Configure l'intervalle avant que le système cherche 'A' (admin uniquement)"""
    global prediction_interval
    try:
        if event.sender_id != ADMIN_ID:
            return

        # Parse command arguments
        message_parts = event.message.message.split()

        if len(message_parts) < 2:
            await event.respond(f"""⏱️ **Configuration de l'Intervalle de Prédiction**

**Usage**: `/intervalle [minutes]`

**Intervalle actuel**: {prediction_interval} minutes

**Description**:
Définit le temps d'attente en minutes avant que le système commence à analyser les messages pour chercher la lettre 'A' dans les parenthèses et déclencher les prédictions.

**Exemples**:
• `/intervalle 3` - Attendre 3 minutes
• `/intervalle 10` - Attendre 10 minutes
• `/intervalle 1` - Attendre 1 minute

**Recommandé**: Entre 1 et 15 minutes""")
            return

        try:
            new_interval = int(message_parts[1])
            if new_interval < 1 or new_interval > 60:
                await event.respond("❌ **Erreur**: L'intervalle doit être entre 1 et 60 minutes")
                return

            old_interval = prediction_interval
            prediction_interval = new_interval

            # Sauvegarder la configuration
            save_config()

            await event.respond(f"""✅ **Intervalle mis à jour**

⏱️ **Ancien intervalle**: {old_interval} minutes
⏱️ **Nouvel intervalle**: {prediction_interval} minutes

Le système attendra maintenant {prediction_interval} minute(s) avant de commencer l'analyse des messages pour la détection des 'A' dans les parenthèses.

Configuration sauvegardée automatiquement.""")

            print(f"✅ Intervalle de prédiction mis à jour: {old_interval} → {prediction_interval} minutes")

        except ValueError:
            await event.respond("❌ **Erreur**: Veuillez entrer un nombre valide de minutes")

    except Exception as e:
        print(f"Erreur dans set_prediction_interval: {e}")
        await event.respond(f"❌ Erreur: {e}")

@client.on(events.NewMessage(pattern='/cooldown'))
async def set_cooldown_interval(event):
    """Configure le cooldown avant re-vérification des règles (admin uniquement)"""
    global cooldown_interval
    try:
        if event.sender_id != ADMIN_ID:
            return

        # Parse command arguments
        message_parts = event.message.message.split()

        if len(message_parts) < 2:
            await event.respond(f"""⏳ **Configuration du Cooldown de Vérification**

**Usage**: `/cooldown [secondes]`

**Cooldown actuel**: {cooldown_interval} secondes

**Description**:
Définit l'intervalle de temps en secondes avant que le bot ne recommence à vérifier les règles de prédiction après un traitement.

**Exemples**:
• `/cooldown 5` - Attendre 5 secondes
• `/cooldown 60` - Attendre 1 minute
• `/cooldown 300` - Attendre 5 minutes

**Plage autorisée**: Entre 0 secondes et 20 minutes (1200 secondes)""")
            return

        try:
            new_cooldown = int(message_parts[1])
            if new_cooldown < 0 or new_cooldown > 1200:  # 0 sec à 20 min
                await event.respond("❌ **Erreur**: Le cooldown doit être entre 0 secondes et 1200 secondes (20 minutes)")
                return

            old_cooldown = cooldown_interval
            cooldown_interval = new_cooldown

            # Sauvegarder la configuration
            save_config()

            # Convertir en format lisible
            if new_cooldown < 60:
                time_display = f"{new_cooldown} secondes"
            else:
                minutes = new_cooldown // 60
                seconds = new_cooldown % 60
                if seconds == 0:
                    time_display = f"{minutes} minute(s)"
                else:
                    time_display = f"{minutes} minute(s) et {seconds} seconde(s)"

            await event.respond(f"""✅ **Cooldown mis à jour**

⏳ **Ancien cooldown**: {old_cooldown} secondes
⏳ **Nouveau cooldown**: {new_cooldown} secondes ({time_display})

Le bot attendra maintenant {time_display} avant de recommencer à vérifier les règles de prédiction.

Configuration sauvegardée automatiquement.""")

            print(f"✅ Cooldown mis à jour: {old_cooldown} → {new_cooldown} secondes")

        except ValueError:
            await event.respond("❌ **Erreur**: Veuillez entrer un nombre valide de secondes")

    except Exception as e:
        print(f"Erreur dans set_cooldown_interval: {e}")
        await event.respond(f"❌ Erreur: {e}")

@client.on(events.NewMessage(pattern='/diagnostic'))
async def run_diagnostic(event):
    """Diagnostic complet du système (admin uniquement)"""
    try:
        if event.sender_id != ADMIN_ID:
            return

        global scheduler
        timestamp = datetime.now().strftime("%H:%M:%S")

        # État des canaux
        stat_status = "✅ Configuré" if detected_stat_channel else "❌ Non configuré"
        display_status = "✅ Configuré" if detected_display_channel else "❌ Non configuré"

        # État du scheduler
        scheduler_status = "🟢 Actif" if scheduler and scheduler.is_running else "🔴 Inactif"

        # Prédictions en cours
        active_predictions = len([s for s in predictor.prediction_status.values() if s == '⌛'])

        # Planification automatique
        auto_schedule_count = 0
        if scheduler and scheduler.schedule_data:
            auto_schedule_count = len(scheduler.schedule_data)

        diagnostic_msg = f"""🔍 **DIAGNOSTIC SYSTÈME** - {timestamp}

📊 **Configuration**:
• Canal stats: {stat_status} ({detected_stat_channel})
• Canal display: {display_status} ({detected_display_channel})
• Cooldown: {cooldown_interval}s
• Intervalle: {prediction_interval}min

🤖 **Scheduler Automatique**:
• Statut: {scheduler_status}
• Planifications: {auto_schedule_count}
• Prédictions actives: {active_predictions}

⚙️ **Fonctionnement**:
• Messages traités: {len(predictor.processed_messages)}
• En attente d'édition: {len(predictor.pending_edit_messages)}

🎯 **Test de Canal**:
• Peut envoyer vers stats: {"✅" if detected_stat_channel else "❌"}
• Peut envoyer vers display: {"✅" if detected_display_channel else "❌"}"""

        await event.respond(diagnostic_msg)

        # Test d'envoi vers le canal de diffusion
        if detected_display_channel:
            try:
                test_msg = f"🧪 Test automatique [{timestamp}] - Bot opérationnel"
                await client.send_message(detected_display_channel, test_msg)
                await event.respond("✅ Test d'envoi vers canal de diffusion réussi")
            except Exception as e:
                await event.respond(f"❌ Échec test canal diffusion: {e}")

    except Exception as e:
        print(f"Erreur diagnostic: {e}")
        await event.respond(f"❌ Erreur diagnostic: {e}")

@client.on(events.NewMessage(pattern='/deploy'))
async def generate_deploy_package(event):
    """Génère le package de déploiement zip40 optimisé pour Render.com avec base YAML (admin uniquement)"""
    try:
        if event.sender_id != ADMIN_ID:
            return

        await event.respond("🚀 **Génération Package ZIP42 - Render.com + Base YAML + Cooldown Corrigé...**")

        try:
            # Créer le package ZIP avec nom zip42
            package_name = 'zip42.zip'

            with zipfile.ZipFile(package_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Fichiers principaux actuels avec toutes les améliorations N3
                files_to_include = [
                    'main.py', 'predictor.py', 'yaml_manager.py', 'scheduler.py'
                ]

                for file_path in files_to_include:
                    if os.path.exists(file_path):
                        zipf.write(file_path)

                # Configuration .env.example pour Render.com
                env_content = f"""# Configuration ZIP42 - Render.com Deployment + Cooldown Corrigé
API_ID=29177661
API_HASH=a8639172fa8d35dbfd8ea46286d349ab
BOT_TOKEN=8134202948:AAFUtAk6Fi0h2fMGERkLzU4UW9GJxdEE_ME
ADMIN_ID=1190237801
RENDER_DEPLOYMENT=true
PORT=10000
PREDICTION_INTERVAL={prediction_interval}
COOLDOWN_INTERVAL={cooldown_interval}"""
                zipf.writestr('.env.example', env_content)

                # requirements.txt pour Replit/Render (versions compatibles)
                requirements_content = """telethon==1.35.0
aiohttp==3.9.5
python-dotenv==1.0.1
pyyaml==6.0.1"""
                zipf.writestr('requirements.txt', requirements_content)

                # runtime.txt pour spécifier la version Python
                runtime_content = "python-3.11.4"
                zipf.writestr('runtime.txt', runtime_content)

                # Documentation ZIP40 pour Render.com
                readme_zip42 = f"""# Package Déploiement ZIP42 - Render.com + Cooldown Corrigé

## 🚀 Fonctionnalités ZIP42:
✅ **Système Cooldown**: Configurez l'intervalle entre vérifications avec /cooldown
✅ **Règles J Strictes**: UN SEUL J dans le deuxième groupe UNIQUEMENT
✅ **Vérification 3K**: Exactement 3 cartes dans le deuxième groupe
✅ **Format 3K**: Messages "🔵XXX 🔵3K: statut :⏳"
✅ **Éditions Temps Réel**: Détection ⏰→🔰/✅ avec traitement différé
✅ **Architecture YAML**: Persistance complète sans PostgreSQL
✅ **Offsets 3**: Vérification ✅0️⃣, ✅1️⃣, ✅2️⃣, ✅3️⃣ ou ❌
✅ **Configuration Persistante**: Sauvegarde automatique JSON + YAML
✅ **Déploiement Render.com**: Optimisé pour déploiement en production
✅ **Base YAML**: Stockage sans PostgreSQL
✅ **Port 10000**: Configuration serveur optimisée

## 🔧 Commandes Disponibles:
• `/cooldown [0-1200]` - Configurer cooldown (0 secondes à 20 minutes)
• `/intervalle [1-60]` - Configurer délai de prédiction
• `/status` - État complet du système
• `/deploy` - Générer package ZIP42
• `/ni` - Informations système de prédiction
• `/sta` - Statut des déclencheurs

## 📋 Règles de Déclenchement:
### ✅ Prédiction générée SEULEMENT si:
- UN SEUL J dans le deuxième groupe
- Message finalisé avec 🔰 ou ✅
- Cooldown respecté entre vérifications
- Exemple: (A♠️2♥️) - (6♥️J♠️) → 🔵X 🔵3K: statut :⏳

### ❌ Pas de prédiction si:
- J dans le premier groupe: (J♠️2♥️) - (6♥️8♠️)
- Plusieurs J dans deuxième: (A♠️2♥️) - (J♥️J♠️)
- Aucun J: (A♠️2♥️) - (6♥️8♠️)
- Message avec ⏰ (en cours d'édition)
- Cooldown actif (évite spam)

### Vérification des Résultats:
- Exactement 3 cartes dans deuxième groupe → Vérification activée
- Calcul des offsets 0, +1, +2, +3 par rapport à la prédiction
- Mise à jour automatique du statut dans le message original
- Gestion automatique des prédictions expirées

## 🗄️ Architecture YAML ZIP42:
- `data/bot_config.yaml`: Configuration persistante
- `data/predictions.yaml`: Historique prédictions 
- `data/auto_predictions.yaml`: Planification automatique
- `data/message_log.yaml`: Logs système
- `bot_config.json`: Backup configuration

## 🌐 Déploiement Render.com:
- Port: 10000 (obligatoire pour Render.com)
- Start Command: `python main.py`
- Build Command: `pip install -r requirements.txt`
- Variables: Pré-configurées dans .env.example
- Base YAML (sans PostgreSQL)

## 📊 Système de Monitoring ZIP42:
- Health check: `http://0.0.0.0:10000/health`
- Status API: `http://0.0.0.0:10000/status`
- Logs détaillés avec timestamps
- Surveillance cooldown en temps réel

## 🎯 Configuration ZIP42:
1. `/intervalle 3` - Prédictions après 3 minutes
2. `/cooldown 30` - Attendre 30 secondes avant re-vérification
3. Render.com: Port 10000 automatiquement configuré
4. Variables d'environnement pré-remplies
5. Base YAML dans dossier `data/`

## 🚀 Déploiement Render.com:
1. Téléchargez zip40.zip
2. Décompressez sur votre machine
3. Créez un nouveau service Web sur Render.com
4. Uploadez les fichiers ou connectez votre repo
5. Les variables sont déjà dans .env.example
6. Déployez directement !

🚀 Package ZIP42 prêt pour Render.com!"""
                zipf.writestr('README_ZIP42.md', readme_zip42)

                # Fichier de configuration Replit
                replit_config = """[deployments.replit]
build = ["pip", "install", "-r", "requirements.txt"]
run = ["python", "main.py"]

[web]
run = ["python", "main.py"]"""
                zipf.writestr('.replit', replit_config)

            file_size = os.path.getsize(package_name) / 1024

            # Envoyer le message de confirmation
            await event.respond(f"""✅ **Package ZIP42 Généré avec Succès!**

📦 **Fichier**: `{package_name}` ({file_size:.1f} KB)

🎯 **Fonctionnalités ZIP42**:
• Système de cooldown configurable (0s-20min) 
• Optimisé pour Render.com
• Architecture YAML complète (sans PostgreSQL)
• Port 10000 pré-configuré
• Variables d'environnement incluses
• Règles J strictes: UN SEUL dans deuxième groupe
• Vérification 3K: exactement 3 cartes

🚀 **Prêt pour Render.com**:
• Variables déjà configurées dans .env.example
• Port 10000 optimisé
• Base YAML (dossier data/)
• Health check intégré

**Package ZIP42 - Déploiement Render.com simplifié + Cooldown Corrigé!**""")

            # Envoyer le fichier ZIP en pièce jointe
            await client.send_file(
                event.chat_id,
                package_name,
                caption="📦 **Package ZIP42 - Render.com Ready** - Base YAML + Port 10000 + Cooldown Corrigé"
            )

            print(f"✅ Package ZIP42 généré: {package_name} ({file_size:.1f} KB)")
            print(f"📋 Fichiers inclus: {len(files_to_include)} fichiers principaux + config")
            print(f"🚀 Optimisé pour Render.com avec base YAML")

        except Exception as e:
            await event.respond(f"❌ Erreur création: {str(e)}")

    except Exception as e:
        print(f"Erreur deploy: {e}")

# --- TRAITEMENT DES MESSAGES DU CANAL DE STATISTIQUES ---
@client.on(events.NewMessage())
@client.on(events.MessageEdited())
async def handle_messages(event):
    """Handle messages from statistics channel"""
    global last_rule_check
    try:
        # Debug: Log ALL incoming messages first with timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        message_text = event.message.message if event.message else "Pas de texte"
        logger.info(f"📬 MESSAGE REÇU: Canal {event.chat_id} | Texte: {message_text[:100]}")

        # Log vers l'admin en cas de prédiction générée
        if detected_stat_channel and event.chat_id == detected_stat_channel:
            logger.info(f"🎯 Message du canal surveillé détecté: {message_text[:200]}")
            try:
                await client.send_message(ADMIN_ID, f"[{timestamp}] 📨 Message surveillé: {message_text[:200]}")
            except Exception as e:
                logger.warning(f"⚠️ Impossible d'envoyer log admin: {e}")

        # Check if stat channel is configured
        if detected_stat_channel is None:
            print("⚠️ PROBLÈME: Canal de statistiques non configuré!")
            return

        # Check if message is from the configured channel
        if event.chat_id != detected_stat_channel:
            print(f"❌ Message ignoré: Canal {event.chat_id} ≠ Canal stats {detected_stat_channel}")
            return

        if not message_text:
            print("❌ Message vide ignoré")
            return

        logger.info(f"✅ TRAITEMENT MESSAGE: Canal {event.chat_id} - {message_text[:50]}...")

        # 1. Vérifier si c'est un message en cours d'édition (⏰ ou 🕐)
        is_pending, game_num = predictor.is_pending_edit_message(message_text)
        if is_pending:
            print(f"⏳ Message #{game_num} mis en attente d'édition finale")
            return  # Ignorer pour le moment, attendre l'édition finale

        # 2. Vérifier le cooldown SEULEMENT pour la génération de nouvelles prédictions
        current_time = datetime.now()
        cooldown_active = False
        if last_rule_check is not None:
            time_since_last_check = (current_time - last_rule_check).total_seconds()
            if time_since_last_check < cooldown_interval:
                cooldown_active = True
                remaining_cooldown = cooldown_interval - time_since_last_check
                logger.debug(f"⏳ Cooldown actif: {remaining_cooldown:.1f}s restantes - Nouvelles prédictions bloquées")

        # 3. Vérifier si c'est l'édition finale d'un message en attente (🔰 ou ✅)
        predicted, predicted_game, suit = predictor.process_final_edit_message(message_text)
        if predicted and not cooldown_active:
            logger.info(f"🎯 ÉDITION FINALE DÉTECTÉE - Génération prédiction #{predicted_game}")
            # Message de prédiction selon le nouveau format
            prediction_text = f"🔵{predicted_game} 🔵3K: statut :⏳"

            sent_messages = await broadcast(prediction_text)

            # Store message IDs for later editing
            if sent_messages and predicted_game:
                for chat_id, message_id in sent_messages:
                    predictor.store_prediction_message(predicted_game, message_id, chat_id)

            # Mettre à jour le timestamp SEULEMENT après génération d'une prédiction
            last_rule_check = current_time
            logger.info(f"✅ PRÉDICTION GÉNÉRÉE APRÈS ÉDITION pour #{predicted_game}: {suit}")
        elif predicted and cooldown_active:
            logger.info(f"⏳ Prédiction après édition bloquée par cooldown pour #{predicted_game}")
        else:
            # 4. Traitement normal des messages (pas d'édition en cours)
            predicted, predicted_game, suit = predictor.should_predict(message_text)
            if predicted and not cooldown_active:
                logger.info(f"🚀 RÈGLE DÉTECTÉE - Génération prédiction #{predicted_game}")
                # Message de prédiction manuelle selon le nouveau format demandé
                prediction_text = f"🔵{predicted_game} 🔵3K: statut :⏳"

                sent_messages = await broadcast(prediction_text)

                # Store message IDs for later editing
                if sent_messages and predicted_game:
                    for chat_id, message_id in sent_messages:
                        predictor.store_prediction_message(predicted_game, message_id, chat_id)

                # Mettre à jour le timestamp SEULEMENT après génération d'une prédiction
                last_rule_check = current_time
                logger.info(f"✅ PRÉDICTION MANUELLE LANCÉE pour #{predicted_game}: {suit}")
            elif predicted and cooldown_active:
                logger.info(f"⏳ Prédiction manuelle bloquée par cooldown pour #{predicted_game}")
            else:
                logger.debug(f"ℹ️ Aucune règle déclenchée pour le message #{predictor.extract_game_number(message_text)}")

        # Check for prediction verification (manuel + automatique)
        verified, number = predictor.verify_prediction(message_text)
        if verified is not None and number is not None:
            statut = predictor.prediction_status.get(number, 'Inconnu')
            logger.info(f"🔍 VÉRIFICATION PRÉDICTION #{number} - Statut: {statut}")
            # Edit the original prediction message instead of sending new message
            success = await edit_prediction_message(number, statut)
            if success:
                logger.info(f"✅ MESSAGE MIS À JOUR #{number}: {statut}")
            else:
                logger.warning(f"⚠️ Échec mise à jour message #{number}, envoi nouveau message")
                status_text = f"🔵{number} 🔵3K: statut :{statut}"
                await broadcast(status_text)

        # Check for expired predictions on every valid result message
        game_number = predictor.extract_game_number(message_text)
        if game_number and not ("⏰" in message_text or "🕐" in message_text):
            expired = predictor.check_expired_predictions(game_number)
            for expired_num in expired:
                # Edit expired prediction messages
                success = await edit_prediction_message(expired_num, '❌')
                if success:
                    print(f"✅ Message de prédiction expirée #{expired_num} mis à jour avec ❌")
                else:
                    print(f"⚠️ Impossible de mettre à jour le message expiré #{expired_num}")
                    status_text = f"🔵{expired_num} 🔵3K: statut :❌"
                    await broadcast(status_text)

        # Vérification des prédictions automatiques du scheduler
        if scheduler and scheduler.schedule_data:
            # Récupère les numéros des prédictions automatiques en attente
            pending_auto_predictions = []
            for numero_str, data in scheduler.schedule_data.items():
                if data["launched"] and not data["verified"]:
                    numero_int = int(numero_str.replace('N', ''))
                    pending_auto_predictions.append(numero_int)

            if pending_auto_predictions:
                # Vérifie si ce message correspond à une prédiction automatique
                predicted_num, status = scheduler.verify_prediction_from_message(message_text, pending_auto_predictions)

                if predicted_num and status:
                    # Met à jour la prédiction automatique
                    numero_str = f"N{predicted_num:03d}"
                    if numero_str in scheduler.schedule_data:
                        data = scheduler.schedule_data[numero_str]
                        data["verified"] = True
                        data["statut"] = status

                        # Met à jour le message
                        await scheduler.update_prediction_message(numero_str, data, status)

                        # Ajouter une nouvelle prédiction pour maintenir la continuité
                        scheduler.add_next_prediction()

                        # Sauvegarde
                        scheduler.save_schedule(scheduler.schedule_data)
                        print(f"📝 Prédiction automatique {numero_str} vérifiée: {status}")
                        print(f"🔄 Nouvelle prédiction générée pour maintenir la continuité")

        # Bilan automatique supprimé sur demande utilisateur

    except Exception as e:
        print(f"Erreur dans handle_messages: {e}")

async def broadcast(message):
    """Broadcast message to display channel"""
    global detected_display_channel

    sent_messages = []
    if detected_display_channel:
        try:
            sent_message = await client.send_message(detected_display_channel, message)
            sent_messages.append((detected_display_channel, sent_message.id))
            logger.info(f"📤 MESSAGE DIFFUSÉ: {message}")
        except Exception as e:
            logger.error(f"❌ Erreur diffusion: {e}")
    else:
        logger.warning("⚠️ Canal d'affichage non configuré")

    return sent_messages

async def edit_prediction_message(game_number: int, new_status: str):
    """Edit prediction message with new status"""
    try:
        message_info = predictor.get_prediction_message(game_number)
        if message_info:
            chat_id = message_info['chat_id']
            message_id = message_info['message_id']
            new_text = f"🔵{game_number} 🔵3K: statut :{new_status}"

            await client.edit_message(chat_id, message_id, new_text)
            print(f"Message de prédiction #{game_number} mis à jour avec statut: {new_status}")
            return True
    except Exception as e:
        print(f"Erreur lors de la modification du message: {e}")
    return False

# Code de génération de rapport supprimé selon demande utilisateur

# --- ENVOI VERS LES CANAUX ---
# (Function moved above to handle message editing)

# --- GESTION D'ERREURS ET RECONNEXION ---
async def handle_connection_error():
    """Handle connection errors and attempt reconnection"""
    print("Tentative de reconnexion...")
    await asyncio.sleep(5)
    try:
        await client.connect()
        print("Reconnexion réussie")
    except Exception as e:
        print(f"Échec de la reconnexion: {e}")

# --- SERVEUR WEB POUR MONITORING ---
async def health_check(request):
    """Health check endpoint"""
    logger.info("📊 Health check accédé")
    return web.Response(text="Bot is running!", status=200)

async def bot_status(request):
    """Bot status endpoint"""
    status = {
        "bot_online": True,
        "stat_channel": detected_stat_channel,
        "display_channel": detected_display_channel,
        "predictions_active": len(predictor.prediction_status),
        "total_predictions": len(predictor.status_log),
        "cooldown_interval": cooldown_interval,
        "prediction_interval": prediction_interval,
        "scheduler_running": scheduler.is_running if scheduler else False
    }
    logger.info(f"📊 Status API accédé: {status}")
    return web.json_response(status)

async def create_web_server():
    """Create and start web server"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    app.router.add_get('/status', bot_status)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"✅ Serveur web démarré sur 0.0.0.0:{PORT}")
    return runner

# --- LANCEMENT ---
async def main():
    """Main function to start the bot"""
    print("Démarrage du bot Telegram...")
    print(f"API_ID: {API_ID}")
    print(f"Bot Token configuré: {'Oui' if BOT_TOKEN else 'Non'}")
    print(f"Port web: {PORT}")

    # Validate configuration
    if not API_ID or not API_HASH or not BOT_TOKEN:
        print("❌ Configuration manquante! Vérifiez votre fichier .env")
        return

    try:
        # Start web server first
        web_runner = await create_web_server()
        logger.info(f"🌐 Serveur web démarré sur port {PORT}")

        # Start the bot
        if await start_bot():
            logger.info("✅ BOT OPÉRATIONNEL - En attente de messages...")
            logger.info(f"🌐 Health check: http://0.0.0.0:{PORT}/health")
            await client.run_until_disconnected()
        else:
            logger.error("❌ ÉCHEC DU DÉMARRAGE DU BOT")

    except KeyboardInterrupt:
        print("\n🛑 Arrêt du bot demandé par l'utilisateur")
    except Exception as e:
        print(f"❌ Erreur critique: {e}")
        await handle_connection_error()
    finally:
        try:
            await client.disconnect()
            print("Bot déconnecté proprement")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())