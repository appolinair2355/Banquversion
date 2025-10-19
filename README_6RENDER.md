# Package Déploiement 6render - Render.com Port 10000

## 🚀 Fonctionnalités 6render:
✅ **Système Cooldown**: Configurez l'intervalle entre vérifications avec /cooldown
✅ **Règles J Strictes**: UN SEUL J dans le deuxième groupe UNIQUEMENT
✅ **Vérification 3K**: Exactement 3 cartes dans le deuxième groupe
✅ **Format 3K**: Messages avec prédiction détaillée
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
- Exemple: (A♠️2♥️) - (6♥️J♠️) → 🔵523 🔵3K: statut :⏳
  Банкир получит 3 карты
  ▪️ Повтор 3 игр (🔰+3)

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

## 🗄️ Architecture YAML 6render:
- `data/bot_config.yaml`: Configuration persistante
- `data/predictions.yaml`: Historique prédictions 
- `data/auto_predictions.yaml`: Planification automatique
- `data/message_log.yaml`: Logs système
- `bot_config.json`: Backup configuration

## 🌐 Déploiement Render.com:
- Port: 10000 (OBLIGATOIRE pour Render.com)
- Start Command: `python main.py`
- Build Command: `pip install -r requirements.txt`
- Variables: Pré-configurées dans .env.example avec PORT=10000
- Base YAML (sans PostgreSQL)

## 📊 Système de Monitoring 6render:
- Health check: `http://0.0.0.0:10000/health`
- Status API: `http://0.0.0.0:10000/status`
- Logs détaillés avec timestamps
- Surveillance cooldown en temps réel

## 🎯 Configuration 6render:
1. `/intervalle 3` - Prédictions après 3 minutes
2. `/cooldown 30` - Attendre 30 secondes avant re-vérification
3. Render.com: Port 10000 pré-configuré
4. Variables d'environnement avec PORT=10000
5. Base YAML dans dossier `data/`

## 🚀 Déploiement Render.com:
1. Téléchargez 6render.zip
2. Décompressez sur votre machine
3. Créez un nouveau service Web sur Render.com
4. Uploadez les fichiers ou connectez votre repo
5. Les variables sont déjà dans .env.example (PORT=10000)
6. Déployez directement !

🚀 Package 6render prêt pour Render.com avec PORT 10000!