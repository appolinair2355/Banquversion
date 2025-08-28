"""
Gestionnaire de données YAML pour le bot Telegram de prédiction
Remplace complètement la base de données PostgreSQL par des fichiers YAML
"""
import os
import yaml
import json
import hashlib
from datetime import datetime, date, time, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path


class YAMLDataManager:
    """Gestionnaire de données basé sur YAML"""
    
    def __init__(self):
        # Répertoire pour stocker tous les fichiers YAML
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        
        # Fichiers de données
        self.config_file = self.data_dir / "bot_config.yaml"
        self.predictions_file = self.data_dir / "predictions.yaml"
        self.auto_predictions_file = self.data_dir / "auto_predictions.yaml"
        self.message_log_file = self.data_dir / "message_log.yaml"
        
        # Initialiser les fichiers s'ils n'existent pas
        self._init_files()
        print("✅ Gestionnaire YAML initialisé")
    
    def _init_files(self):
        """Initialise les fichiers YAML s'ils n'existent pas"""
        default_structures = {
            self.config_file: {},
            self.predictions_file: [],
            self.auto_predictions_file: {},
            self.message_log_file: []
        }
        
        for file_path, default_content in default_structures.items():
            if not file_path.exists():
                self._save_yaml(file_path, default_content)
    
    def _load_yaml(self, file_path: Path) -> Any:
        """Charge un fichier YAML"""
        try:
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            return {}
        except Exception as e:
            print(f"❌ Erreur chargement {file_path}: {e}")
            return {}
    
    def _save_yaml(self, file_path: Path, data: Any):
        """Sauvegarde des données dans un fichier YAML"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, indent=2)
        except Exception as e:
            print(f"❌ Erreur sauvegarde {file_path}: {e}")
    
    def set_config(self, key: str, value: Any):
        """Sauvegarde une valeur de configuration"""
        try:
            config = self._load_yaml(self.config_file)
            config[key] = {
                'value': value,
                'updated_at': datetime.now().isoformat()
            }
            self._save_yaml(self.config_file, config)
        except Exception as e:
            print(f"❌ Erreur set_config: {e}")
    
    def get_config(self, key: str, default=None):
        """Récupère une valeur de configuration"""
        try:
            config = self._load_yaml(self.config_file)
            if key in config:
                return config[key]['value']
            return default
        except Exception as e:
            print(f"❌ Erreur get_config: {e}")
            return default
    
    def save_prediction(self, game_number: int, suit_combination: str, 
                       message_id: Optional[int] = None, chat_id: Optional[int] = None, 
                       prediction_type: str = 'manual'):
        """Sauvegarde une prédiction manuelle"""
        try:
            predictions = self._load_yaml(self.predictions_file)
            if not isinstance(predictions, list):
                predictions = []
            
            # Vérifier si la prédiction existe déjà
            existing = any(p.get('game_number') == game_number for p in predictions)
            if existing:
                return
            
            prediction = {
                'id': len(predictions) + 1,
                'game_number': game_number,
                'suit_combination': suit_combination,
                'status': '⌛',
                'message_id': message_id,
                'chat_id': chat_id,
                'created_at': datetime.now().isoformat(),
                'verified_at': None,
                'prediction_type': prediction_type
            }
            
            predictions.append(prediction)
            self._save_yaml(self.predictions_file, predictions)
        except Exception as e:
            print(f"❌ Erreur save_prediction: {e}")
    
    def update_prediction_status(self, game_number: int, status: str):
        """Met à jour le statut d'une prédiction"""
        try:
            predictions = self._load_yaml(self.predictions_file)
            if not isinstance(predictions, list):
                return
            
            for prediction in predictions:
                if prediction.get('game_number') == game_number:
                    prediction['status'] = status
                    prediction['verified_at'] = datetime.now().isoformat()
                    break
            
            self._save_yaml(self.predictions_file, predictions)
        except Exception as e:
            print(f"❌ Erreur update_prediction_status: {e}")
    
    def get_pending_predictions(self) -> List[Dict]:
        """Récupère les prédictions en attente"""
        try:
            predictions = self._load_yaml(self.predictions_file)
            if not isinstance(predictions, list):
                return []
            
            return [p for p in predictions if p.get('status') == '⌛']
        except Exception as e:
            print(f"❌ Erreur get_pending_predictions: {e}")
            return []
    
    def update_prediction_status(self, game_number: int, new_status: str):
        """Met à jour le statut d'une prédiction existante"""
        try:
            predictions = self._load_yaml(self.predictions_file)
            if not isinstance(predictions, list):
                predictions = []
            
            # Trouver et mettre à jour la prédiction
            updated = False
            for prediction in predictions:
                if prediction.get('game_number') == game_number:
                    old_status = prediction.get('status', 'inconnu')
                    prediction['status'] = new_status
                    prediction['verified_at'] = datetime.now().isoformat()
                    updated = True
                    print(f"📁 Prédiction #{game_number}: {old_status} → {new_status}")
                    break
            
            if updated:
                self._save_yaml(self.predictions_file, predictions)
                return True
            else:
                print(f"⚠️ Prédiction #{game_number} non trouvée dans YAML")
                return False
                
        except Exception as e:
            print(f"❌ Erreur update_prediction_status: {e}")
            return False
    
    def save_auto_prediction_schedule(self, schedule_data: Dict[str, Any]):
        """Sauvegarde la planification automatique complète"""
        try:
            # Ajouter la date courante pour organiser par jour
            today = date.today().isoformat()
            auto_predictions = self._load_yaml(self.auto_predictions_file)
            
            if not isinstance(auto_predictions, dict):
                auto_predictions = {}
            
            # Remplacer la planification du jour
            auto_predictions[today] = schedule_data
            
            self._save_yaml(self.auto_predictions_file, auto_predictions)
        except Exception as e:
            print(f"❌ Erreur save_auto_prediction_schedule: {e}")
    
    def load_auto_prediction_schedule(self) -> Dict[str, Any]:
        """Charge la planification automatique du jour"""
        try:
            today = date.today().isoformat()
            auto_predictions = self._load_yaml(self.auto_predictions_file)
            
            if not isinstance(auto_predictions, dict):
                return {}
            
            return auto_predictions.get(today, {})
        except Exception as e:
            print(f"❌ Erreur load_auto_prediction_schedule: {e}")
            return {}
    
    def update_auto_prediction(self, numero: str, updates: Dict[str, Any]):
        """Met à jour une prédiction automatique"""
        try:
            today = date.today().isoformat()
            auto_predictions = self._load_yaml(self.auto_predictions_file)
            
            if not isinstance(auto_predictions, dict):
                auto_predictions = {}
            
            if today not in auto_predictions:
                auto_predictions[today] = {}
            
            if numero in auto_predictions[today]:
                auto_predictions[today][numero].update(updates)
                self._save_yaml(self.auto_predictions_file, auto_predictions)
        except Exception as e:
            print(f"❌ Erreur update_auto_prediction: {e}")
    
    def is_message_processed(self, message_content: str, channel_id: int) -> bool:
        """Vérifie si un message a déjà été traité"""
        try:
            message_hash = hashlib.sha256(f"{channel_id}:{message_content}".encode()).hexdigest()
            message_log = self._load_yaml(self.message_log_file)
            
            if not isinstance(message_log, list):
                return False
            
            return any(msg.get('message_hash') == message_hash for msg in message_log)
        except Exception as e:
            print(f"❌ Erreur is_message_processed: {e}")
            return False
    
    def mark_message_processed(self, message_content: str, channel_id: int):
        """Marque un message comme traité"""
        try:
            message_hash = hashlib.sha256(f"{channel_id}:{message_content}".encode()).hexdigest()
            message_log = self._load_yaml(self.message_log_file)
            
            if not isinstance(message_log, list):
                message_log = []
            
            # Vérifier si déjà traité
            if any(msg.get('message_hash') == message_hash for msg in message_log):
                return
            
            message_entry = {
                'id': len(message_log) + 1,
                'message_hash': message_hash,
                'channel_id': channel_id,
                'content': message_content,
                'processed_at': datetime.now().isoformat()
            }
            
            message_log.append(message_entry)
            
            # Garder seulement les 1000 derniers messages pour éviter que le fichier devienne trop gros
            if len(message_log) > 1000:
                message_log = message_log[-1000:]
            
            self._save_yaml(self.message_log_file, message_log)
        except Exception as e:
            print(f"❌ Erreur mark_message_processed: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du bot"""
        try:
            # Statistiques des prédictions manuelles
            predictions = self._load_yaml(self.predictions_file)
            if not isinstance(predictions, list):
                predictions = []
            
            manual_stats = {
                'total': len(predictions),
                'success': len([p for p in predictions if p.get('status', '').startswith('✅')]),
                'pending': len([p for p in predictions if p.get('status') == '⌛'])
            }
            
            # Statistiques des prédictions automatiques
            today = date.today().isoformat()
            auto_predictions = self._load_yaml(self.auto_predictions_file)
            
            if not isinstance(auto_predictions, dict):
                auto_predictions = {}
            
            today_schedule = auto_predictions.get(today, {})
            
            auto_stats = {
                'total': len(today_schedule),
                'launched': len([p for p in today_schedule.values() if p.get('launched', False)]),
                'verified': len([p for p in today_schedule.values() if p.get('verified', False)])
            }
            
            return {
                'manual': manual_stats,
                'auto': auto_stats
            }
        except Exception as e:
            print(f"❌ Erreur get_stats: {e}")
            return {'manual': {}, 'auto': {}}
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Nettoie les anciennes données (optionnel)"""
        try:
            cutoff_date = datetime.now().date() - timedelta(days=days_to_keep)
            
            # Nettoyer les anciennes prédictions automatiques
            auto_predictions = self._load_yaml(self.auto_predictions_file)
            if isinstance(auto_predictions, dict):
                cleaned = {
                    date_str: data for date_str, data in auto_predictions.items()
                    if datetime.fromisoformat(date_str).date() >= cutoff_date
                }
                if len(cleaned) != len(auto_predictions):
                    self._save_yaml(self.auto_predictions_file, cleaned)
                    print(f"🧹 Nettoyage: {len(auto_predictions) - len(cleaned)} anciennes planifications supprimées")
        except Exception as e:
            print(f"❌ Erreur cleanup_old_data: {e}")


# Instance globale
yaml_manager = None

def init_yaml_manager():
    """Initialise le gestionnaire YAML"""
    global yaml_manager
    try:
        yaml_manager = YAMLDataManager()
        return yaml_manager
    except Exception as e:
        print(f"❌ Erreur initialisation gestionnaire YAML: {e}")
        return None

# Alias pour compatibilité avec l'ancien code
db = None

def init_database():
    """Initialise le gestionnaire de données (alias pour compatibilité)"""
    global db
    db = init_yaml_manager()
    return db