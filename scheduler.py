import random
import asyncio
import yaml
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from telethon import TelegramClient

class PredictionScheduler:
    """Système de planification automatique des prédictions"""
    
    def __init__(self, client: TelegramClient, predictor, source_channel_id: int, target_channel_id: int):
        """
        Initialise le planificateur
        
        Args:
            client: Client Telegram
            predictor: Instance du CardPredictor
            source_channel_id: ID du canal source pour vérification
            target_channel_id: ID du canal cible pour diffusion
        """
        self.client = client
        self.predictor = predictor
        self.source_channel_id = source_channel_id
        self.target_channel_id = target_channel_id
        self.schedule_file = "prediction.yaml"
        self.is_running = False
        self.schedule_data = {}
        
    def generate_next_prediction_time(self, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Génère la prochaine prédiction avec lancement variable (1-4 min avant)"""
        if current_time is None:
            current_time = datetime.now()
        
        # Ajouter un intervalle fixe pour la prochaine prédiction (ex: 1 heure)
        next_time = current_time + timedelta(hours=1)
        
        # Générer un numéro de prédiction basé sur l'heure
        # Format: heure + minutes (ex: 7:30 -> N730)
        numero_predit = f"N{next_time.hour:02d}{next_time.minute:02d}"
        
        # VARIABLE: Heure de lancement entre 1-4 minutes avant la prédiction
        launch_offset_minutes = random.randint(1, 4)  # 1-4 minutes avant comme demandé
        launch_time = next_time - timedelta(minutes=launch_offset_minutes)
        
        prediction_data = {
            "numero": numero_predit,
            "heure_lancement": launch_time.strftime("%H:%M"),
            "heure_prediction": next_time.strftime("%H:%M"),
            "statut": "⌛",
            "message_id": None,
            "chat_id": None,
            "launched": False,
            "verified": False,
            "generated_at": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "launch_offset": launch_offset_minutes
        }
        
        return prediction_data

    def generate_daily_schedule(self) -> Dict[str, Any]:
        """Génère une planification avec heures de lancement variables"""
        planification = {}
        current_time = datetime.now()
        
        # Générer des prédictions toutes les heures avec lancement variable
        num_predictions = 12  # 12 prédictions sur 12 heures
        
        for i in range(num_predictions):
            # Calculer l'heure de prédiction (toutes les heures)
            prediction_time = current_time + timedelta(hours=i+1)
            
            # Générer numéro basé sur l'heure de prédiction
            numero = f"N{prediction_time.hour:02d}{prediction_time.minute:02d}"
            
            # VARIABLE: Lancement entre 1-4 minutes avant comme demandé
            launch_offset_minutes = random.randint(1, 4)
            launch_time = prediction_time - timedelta(minutes=launch_offset_minutes)
            
            # Éviter les doublons de numéros
            counter = 0
            original_numero = numero
            while numero in planification:
                counter += 1
                numero = f"{original_numero}_{counter}"
            
            planification[numero] = {
                "heure_lancement": launch_time.strftime("%H:%M"),
                "heure_prediction": prediction_time.strftime("%H:%M"),
                "statut": "⌛",
                "message_id": None,
                "chat_id": None,
                "launched": False,
                "verified": False,
                "generated_at": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "launch_offset": launch_offset_minutes
            }
        
        print(f"✅ Planification avec lancement variable générée: {num_predictions} prédictions")
        print(f"    Variations de lancement: 1-4 minutes avant chaque prédiction")
        return planification
    
    def save_schedule(self, schedule_data: Dict[str, Any]):
        """Sauvegarde la planification dans le fichier YAML"""
        try:
            with open(self.schedule_file, "w", encoding='utf-8') as f:
                yaml.dump(schedule_data, f, allow_unicode=True, default_flow_style=False)
            print(f"✅ Planification sauvegardée dans {self.schedule_file}")
        except Exception as e:
            print(f"❌ Erreur sauvegarde planification: {e}")
    
    def load_schedule(self) -> Dict[str, Any]:
        """Charge la planification depuis le fichier YAML"""
        try:
            if os.path.exists(self.schedule_file):
                with open(self.schedule_file, "r", encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                print(f"✅ Planification chargée: {len(data)} entrées")
                return data
            else:
                print("ℹ️ Aucune planification existante, génération d'une nouvelle")
                return {}
        except Exception as e:
            print(f"❌ Erreur chargement planification: {e}")
            return {}
    
    def get_current_time_slot(self) -> str:
        """Retourne le créneau horaire actuel au format HH:MM"""
        now = datetime.now()
        return now.strftime("%H:%M")
    
    def get_pending_launches(self, current_time: str) -> list:
        """Retourne les prédictions à lancer pour l'heure actuelle"""
        pending = []
        for numero, data in self.schedule_data.items():
            if (data["heure_lancement"] == current_time and 
                not data["launched"] and 
                data["statut"] == "⌛"):
                pending.append((numero, data))
        return pending
    
    def add_next_prediction(self):
        """Ajoute une nouvelle prédiction à la planification"""
        try:
            new_prediction = self.generate_next_prediction_time()
            numero = new_prediction.pop("numero")
            
            # Éviter les doublons
            counter = 1
            original_numero = numero
            while numero in self.schedule_data:
                # Modifier légèrement le numéro si doublon
                base_num = int(original_numero[1:])
                numero = f"N{base_num + counter:04d}"
                counter += 1
            
            self.schedule_data[numero] = new_prediction
            self.save_schedule(self.schedule_data)
            
            print(f"✅ Nouvelle prédiction ajoutée: {numero} à {new_prediction['heure_lancement']}")
            return numero
            
        except Exception as e:
            print(f"❌ Erreur ajout prédiction: {e}")
            return None
    
    def get_predictions_to_verify(self) -> list:
        """Retourne les prédictions à vérifier"""
        to_verify = []
        for numero, data in self.schedule_data.items():
            if (data["launched"] and 
                not data["verified"] and 
                data["message_id"] is not None):
                to_verify.append((numero, data))
        return to_verify
    
    async def launch_prediction(self, numero: str, data: Dict[str, Any]):
        """Lance une prédiction automatique selon le nouveau format"""
        try:
            # Vérifier les doublons avant de lancer
            game_number = int(numero.replace('N', ''))
            if game_number in self.predictor.prediction_status:
                print(f"❌ Prédiction déjà existante pour {numero}, abandon du lancement automatique")
                return False
            
            # Marquer comme prédiction automatique pour éviter les conflits
            self.predictor.processed_messages.add(f"auto_prediction_{game_number}")
            
            # Génère une prédiction aléatoire de couleurs (2K/2K format)
            suit_prediction = self.generate_suit_prediction()
            
            # Message de prédiction automatique selon le nouveau format demandé
            game_number = int(numero.replace('N', ''))
            prediction_text = f"🔵{game_number} 🔵2D: {suit_prediction} :⏳"
            
            # Envoie le message au canal cible
            sent_message = await self.client.send_message(self.target_channel_id, prediction_text)
            
            # Met à jour les données
            data["launched"] = True
            data["message_id"] = sent_message.id
            data["chat_id"] = self.target_channel_id
            data["prediction_format"] = suit_prediction
            
            # Ajouter à la prédiction status pour éviter les doublons
            self.predictor.prediction_status[game_number] = '⌛'
            
            # IMPORTANT: Mettre à jour le cooldown pour les prédictions automatiques
            # Importer la variable globale depuis main
            import main
            main.last_rule_check = datetime.now()
            print(f"🔄 Cooldown mis à jour après prédiction automatique {numero}")
            
            # Sauvegarde
            self.save_schedule(self.schedule_data)
            
            print(f"🚀 Prédiction automatique lancée: {numero} ({suit_prediction}) à {data['heure_lancement']}")
            return True
            
        except Exception as e:
            print(f"❌ Erreur lancement prédiction {numero}: {e}")
            return False
    
    def generate_suit_prediction(self) -> str:
        """Génère une prédiction au format 2K/2K"""
        # Formats possibles pour les prédictions automatiques
        formats = [
            "2K/2K",   # 2 couleurs différentes / 2 couleurs différentes
            "2P/2P",   # 2 paires / 2 paires  
            "2C/2C",   # 2 coeurs / 2 coeurs
            "2T/2T"    # 2 trèfles / 2 trèfles
        ]
        return random.choice(formats)
    
    async def verify_prediction_status(self, numero: str, data: Dict[str, Any]):
        """
        Vérifie le statut d'une prédiction selon l'algorithme spécifié :
        1. Vérifie le numéro exact (offset 0) → ✅0️⃣
        2. Vérifie le numéro suivant (offset 1) → ✅1️⃣  
        3. Vérifie le numéro +2 (offset 2) → ✅2️⃣
        4. Sinon → 📌❌
        """
        print(f"🔍 Vérification du statut pour {numero}")
        
        # Cette fonction sera appelée depuis le bot principal lors du traitement des messages
        # Elle ne fait plus de requêtes API directes mais utilise les messages reçus
        return False
    
    async def update_prediction_message(self, numero: str, data: Dict[str, Any], new_status: str):
        """Met à jour le message de prédiction avec le nouveau statut"""
        try:
            if data["message_id"] and data["chat_id"]:
                # Message mis à jour selon le nouveau format demandé
                game_number = int(numero.replace('N', ''))
                new_text = f"🔵{game_number} 🔵2D: statut :{new_status}"

                await self.client.edit_message(
                    data["chat_id"], 
                    data["message_id"], 
                    new_text
                )
                print(f"📝 Message automatique {numero} mis à jour: {new_status}")
        except Exception as e:
            print(f"❌ Erreur mise à jour message {numero}: {e}")
    
    def check_card_distribution(self, group1: str, group2: str) -> bool:
        """
        Vérifie si chaque groupe a exactement 2 cartes (symboles)
        Selon l'algorithme : ne compte que ♠️, ♣️, ♥️, ♦️
        """
        def count_cards(symbols_str: str) -> int:
            # Compter d'abord les versions emoji, puis les versions simples
            emoji_symbols = ['♠️', '♥️', '♦️', '♣️']
            simple_symbols = ['♠', '♥', '♦', '♣']
            
            temp_str = symbols_str
            emoji_count = 0
            
            for emoji in emoji_symbols:
                count = temp_str.count(emoji)
                emoji_count += count
                temp_str = temp_str.replace(emoji, 'X')
            
            simple_count = 0
            for symbol in simple_symbols:
                simple_count += temp_str.count(symbol)
                
            return emoji_count + simple_count
        
        count1 = count_cards(group1)
        count2 = count_cards(group2)
        
        print(f"🃏 Comptage cartes: groupe1='{group1}'→{count1}, groupe2='{group2}'→{count2}")
        return count1 == 2 and count2 == 2
    
    def verify_prediction_from_message(self, message_text: str, predicted_numbers: list) -> tuple:
        """
        Vérifie une prédiction selon l'algorithme spécifié :
        1. Cherche le numéro exact (offset 0) → ✅0️⃣
        2. Cherche le numéro suivant (offset 1) → ✅1️⃣  
        3. Cherche le numéro +2 (offset 2) → ✅2️⃣
        4. Sinon → 📌❌
        """
        import re
        
        # Extrait le numéro du message
        match = re.search(r"#N(\d+)\.", message_text)
        if not match:
            return None, None
        
        current_number = int(match.group(1))
        print(f"🔍 Message reçu pour #N{current_number}")
        
        # Extrait les groupes de cartes entre parenthèses
        groups = re.findall(r"\(([^)]*)\)", message_text)
        if len(groups) < 2:
            print(f"❌ Groupes insuffisants dans le message: {groups}")
            return None, None
        
        group1, group2 = groups[0], groups[1]
        
        # Vérifie si ce message correspond à une prédiction
        for predicted_num in predicted_numbers:
            # Offsets possibles : 0, 1, 2
            for offset in range(3):
                target_number = predicted_num + offset
                
                if current_number == target_number:
                    print(f"🎯 Correspondance trouvée: prédiction N{predicted_num:03d} vs message N{current_number} (offset {offset})")
                    
                    # Vérifie la distribution des cartes
                    if self.check_card_distribution(group1, group2):
                        # Détermine le statut selon l'offset
                        if offset == 0:
                            status = "✅0️⃣"
                        elif offset == 1:
                            status = "✅1️⃣"
                        else:  # offset == 2
                            status = "✅2️⃣"
                        
                        print(f"✅ Prédiction réussie N{predicted_num:03d}: {status}")
                        return predicted_num, status
                    else:
                        # Distribution incorrecte
                        print(f"❌ Distribution incorrecte pour N{predicted_num:03d}")
                        return predicted_num, "📌❌"
        
        return None, None
    
    async def run_scheduler(self):
        """Boucle principale du planificateur"""
        print("🚀 Démarrage du planificateur automatique")
        
        # Charge ou génère la planification
        self.schedule_data = self.load_schedule()
        if not self.schedule_data:
            self.schedule_data = self.generate_daily_schedule()
            self.save_schedule(self.schedule_data)
        
        self.is_running = True
        
        while self.is_running:
            try:
                current_time = self.get_current_time_slot()
                
                # Lance les prédictions en attente
                pending_launches = self.get_pending_launches(current_time)
                for numero, data in pending_launches:
                    await self.launch_prediction(numero, data)
                
                # Les vérifications automatiques sont maintenant gérées 
                # directement dans handle_messages() lors de la réception des messages
                
                # Attendre 30 secondes avant le prochain cycle
                await asyncio.sleep(30)
                
            except Exception as e:
                print(f"❌ Erreur dans le planificateur: {e}")
                await asyncio.sleep(60)  # Attendre plus longtemps en cas d'erreur
    
    def stop_scheduler(self):
        """Arrête le planificateur"""
        self.is_running = False
        print("🛑 Planificateur arrêté")
    
    def get_schedule_status(self) -> Dict[str, Any]:
        """Retourne le statut actuel de la planification"""
        if not self.schedule_data:
            return {"error": "Aucune planification chargée"}
        
        total = len(self.schedule_data)
        launched = sum(1 for data in self.schedule_data.values() if data["launched"])
        verified = sum(1 for data in self.schedule_data.values() if data["verified"])
        pending = total - launched
        
        # Prochaine prédiction
        current_time = self.get_current_time_slot()
        next_launch = None
        for numero, data in self.schedule_data.items():
            if not data["launched"] and data["heure_lancement"] > current_time:
                next_launch = f"{numero} à {data['heure_lancement']}"
                break
        
        return {
            "total": total,
            "launched": launched,
            "verified": verified,
            "pending": pending,
            "next_launch": next_launch,
            "is_running": self.is_running
        }
    
    def regenerate_schedule(self):
        """Régénère une nouvelle planification quotidienne"""
        self.schedule_data = self.generate_daily_schedule()
        self.save_schedule(self.schedule_data)
        print("🔄 Nouvelle planification générée")

# Exemple d'utilisation
if __name__ == "__main__":
    # Génération d'un exemple de planification
    from unittest.mock import Mock
    mock_client = Mock()
    mock_predictor = Mock()
    scheduler = PredictionScheduler(mock_client, mock_predictor, 0, 0)
    schedule = scheduler.generate_daily_schedule()
    scheduler.schedule_data = schedule
    scheduler.save_schedule(schedule)
    print("✅ Exemple de planification généré dans prediction.yaml")