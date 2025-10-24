# 🔧 Guide Rapide de Correction du Bug de Synchronisation

## 🐛 Problème
124 commandes du 26/09/2025 marquées `SYNCED` mais sans `onlineId` → 1,976,000 FC manquants

## ✅ Solution en 3 Fichiers

### 1️⃣ Documentation Complète
**Fichier:** `FIX_ANDROID_SYNC.md`
- Analyse détaillée du bug
- Code corrigé avec explications
- Tests de validation
- Checklist de déploiement

### 2️⃣ Patch Git
**Fichier:** `android_sync_fix.patch`
- Patch au format unified diff
- Application avec `git apply` ou manuellement

### 3️⃣ Script Automatisé
**Fichier:** `apply_android_fix.ps1`
- Automatise toute la procédure
- Backup + Patch + Compilation + Installation + Re-sync

---

## 🚀 Application Rapide (PowerShell)

```powershell
# Lancer le script automatique
cd c:\odoo\server\odoo\addons\pos_caisse
.\apply_android_fix.ps1
```

Le script fait tout :
1. ✅ Backup DB + Code
2. ✅ Application du patch
3. ✅ Compilation APK
4. ✅ Installation (optionnel)
5. ✅ Re-sync 124 commandes
6. ✅ Vérification finale

---

## 🔧 Application Manuelle

### Étape 1 : Backup
```powershell
# Base de données
Copy-Item pos_offline.bdd pos_offline_backup.bdd

# Code source
cd c:\Users\arnol\Documents\ProjetsAndroid\pos_mobile_sumni\app\src\main\java\com\bulkasoft\pos\data\sync
Copy-Item SyncRepository.kt SyncRepository.kt.bak
```

### Étape 2 : Modifier le code
Ouvrir `SyncRepository.kt` et appliquer ces 3 corrections :

#### A) Ligne 160-174 - Méthode `pushOne()`
```kotlin
// REMPLACER
if (resp.isSuccessful || resp.code() == 409) {
    val onlineId = extractOnlineId(resp)
    dao.markSynced(cmd.localId, onlineId, LocalCommande.Status.SYNCED, System.currentTimeMillis())
    Log.d("SyncRepository", "pushOne: marked SYNCED localId=${cmd.localId} onlineId=${onlineId}")
    true
}

// PAR
if (resp.isSuccessful || resp.code() == 409) {
    val onlineId = extractOnlineId(resp)
    
    // VALIDATION STRICTE : onlineId OBLIGATOIRE
    if (onlineId != null) {
        dao.markSynced(cmd.localId, onlineId, LocalCommande.Status.SYNCED, System.currentTimeMillis())
        Log.d("SyncRepository", "pushOne: SUCCESS - marked SYNCED localId=${cmd.localId} onlineId=${onlineId}")
        true
    } else {
        Log.w("SyncRepository", "pushOne: ANOMALY - server accepted but onlineId=null, marking FAILED localId=${cmd.localId}")
        dao.markFailed(cmd.localId, LocalCommande.Status.FAILED, System.currentTimeMillis())
        false
    }
}
```

#### B) Ligne 119-127 - Méthode `createOrQueueCommande()`
```kotlin
// REMPLACER
if (resp.isSuccessful || resp.code() == 409) {
    val onlineId = extractOnlineId(resp)
    Log.d("SyncRepository", "createOrQueue: server accepted, onlineId=$onlineId")
    saveMirrorSynced(clientCard, clientName, typePaiement, totalFc, lignes, key, onlineId, sessionId, isVc)
    return@withContext true
}

// PAR
if (resp.isSuccessful || resp.code() == 409) {
    val onlineId = extractOnlineId(resp)
    
    // VALIDATION STRICTE : onlineId OBLIGATOIRE
    if (onlineId != null) {
        Log.d("SyncRepository", "createOrQueue: SUCCESS - server accepted, onlineId=$onlineId")
        saveMirrorSynced(clientCard, clientName, typePaiement, totalFc, lignes, key, onlineId, sessionId, isVc)
        return@withContext true
    } else {
        Log.w("SyncRepository", "createOrQueue: ANOMALY - server accepted but onlineId=null, queueing idemKey=$key")
        saveLocalCommande(clientCard, clientName, typePaiement, totalFc, lignes, key, sessionId, isVc)
        return@withContext false
    }
}
```

#### C) Ligne 36-50 - Méthode `extractOnlineId()`
```kotlin
// REMPLACER
if (idFromBody != null) return idFromBody
val location = resp.headers()["Location"]
location?.substringAfterLast('/')?.toLongOrNull()

// PAR
if (idFromBody != null) {
    Log.d("SyncRepository", "extractOnlineId: found in body = $idFromBody")
    return idFromBody
}

val location = resp.headers()["Location"]
val idFromLocation = location?.substringAfterLast('/')?.toLongOrNull()
if (idFromLocation != null) {
    Log.d("SyncRepository", "extractOnlineId: found in Location header = $idFromLocation")
    return idFromLocation
}

Log.w("SyncRepository", "extractOnlineId: FAILED - no onlineId found. Response code=${resp.code()}")
null
```

### Étape 3 : Compiler
```powershell
cd c:\Users\arnol\Documents\ProjetsAndroid\pos_mobile_sumni
.\gradlew.bat clean
.\gradlew.bat assembleRelease
```

APK généré : `app\build\outputs\apk\release\app-release.apk`

### Étape 4 : Installer
```powershell
# Via ADB
adb install -r app\build\outputs\apk\release\app-release.apk

# OU copier l'APK et installer manuellement sur l'appareil
```

### Étape 5 : Re-synchroniser
```powershell
cd c:\odoo\server\odoo\addons\pos_caisse
python scripts/resync_orphan_commandes.py --username arnold --password "Limon@de1" --date 2025-09-26
```

### Étape 6 : Vérifier
```powershell
# Vérifier aucune commande SYNCED sans onlineId
python scripts/query_db.py --stats

# Comparer local vs online
python scripts/compare_date.py --date 2025-09-26
```

---

## 🧪 Tests de Validation

### Test 1 : Création commande online
```kotlin
// Dans l'app Android
1. Créer une commande
2. Vérifier dans les logs : "SUCCESS - marked SYNCED ... onlineId=XXX"
3. Vérifier en DB : SELECT * FROM local_commandes WHERE localId=XXX
   → status='SYNCED' ET onlineId IS NOT NULL
```

### Test 2 : Simulation échec réseau
```kotlin
// Couper le WiFi/4G pendant création commande
1. Créer une commande (réseau coupé)
2. Vérifier logs : "network error, queueing"
3. Vérifier DB : status='LOCAL'
4. Rallumer réseau
5. Cliquer "Synchroniser"
6. Vérifier logs : "SUCCESS - marked SYNCED"
7. Vérifier DB : status='SYNCED' ET onlineId IS NOT NULL
```

### Test 3 : Simulation onlineId null
```kotlin
// Nécessite modification temporaire du serveur pour retourner 200 sans onlineId
1. Créer commande
2. Vérifier logs : "ANOMALY - server accepted but onlineId=null, marking FAILED"
3. Vérifier DB : status='FAILED' (pas SYNCED !)
4. La commande sera re-tentée au prochain sync
```

---

## 📊 Vérification Post-Fix

### SQL à exécuter
```sql
-- Doit retourner 0 après le fix
SELECT COUNT(*) FROM local_commandes 
WHERE status = 'SYNCED' AND onlineId IS NULL;

-- Vérifier distribution des statuts
SELECT status, COUNT(*) as nb, SUM(total) as total_fc
FROM local_commandes 
GROUP BY status;

-- Vérifier 26/09/2025
SELECT status, COUNT(*) as nb
FROM local_commandes 
WHERE date = '2025-09-26'
GROUP BY status;
```

### Résultats attendus
```
status=SYNCED, nb=245, avec onlineId=245  ✅
status=LOCAL, nb=0                         ✅
status=FAILED, nb=0 (ou en cours de retry) ✅

Total 26/09: 245 local = 245 online        ✅
```

---

## 🎯 Checklist de Déploiement

- [ ] **Backup effectué** (DB + Code)
- [ ] **Patch appliqué** (3 modifications dans SyncRepository.kt)
- [ ] **Compilation OK** (APK généré)
- [ ] **Tests manuels OK** (création + sync + échec)
- [ ] **Re-sync 124 commandes OK** (script Python)
- [ ] **Vérification SQL OK** (0 orphans SYNCED)
- [ ] **Comparaison locale/online OK** (245 = 245)
- [ ] **APK déployé** (tous les appareils)
- [ ] **Formation équipe** (nouveaux logs)
- [ ] **Documentation MAJ**

---

## 📞 En Cas de Problème

### Rollback complet
```powershell
# Restaurer code source
cd c:\Users\arnol\Documents\ProjetsAndroid\pos_mobile_sumni\app\src\main\java\com\bulkasoft\pos\data\sync
Copy-Item SyncRepository.kt.bak SyncRepository.kt -Force

# Recompiler version précédente
cd c:\Users\arnol\Documents\ProjetsAndroid\pos_mobile_sumni
.\gradlew.bat assembleRelease

# Réinstaller
adb install -r app\build\outputs\apk\release\app-release.apk
```

### Logs de debug
```powershell
# Suivre les logs Android en temps réel
adb logcat | Select-String "SyncRepository"

# Filtrer seulement les erreurs
adb logcat | Select-String "SyncRepository.*ERROR|ANOMALY|FAILED"

# Sauvegarder les logs
adb logcat > android_sync_logs.txt
```

---

## 📚 Fichiers de Référence

| Fichier | Description |
|---------|-------------|
| `FIX_ANDROID_SYNC.md` | Documentation complète du fix |
| `android_sync_fix.patch` | Patch Git (unified diff) |
| `apply_android_fix.ps1` | Script PowerShell automatisé |
| `resync_orphan_commandes.py` | Script Python de re-sync |
| `QUICKSTART.md` | Ce fichier (guide rapide) |

---

## ✅ Statut Final Attendu

Après application complète du fix :

```
✅ 0 commandes SYNCED sans onlineId
✅ 6,222 commandes total synchronisées
✅ 128,952,000 FC comptabilisés
✅ 100% d'intégrité locale/online
✅ Retry automatique pour échecs réseau
✅ Logs détaillés pour debugging
```

---

**Auteur:** Arnold  
**Date:** 2025-01-XX  
**Version:** 1.0  
**Projet:** POS Mobile Sumni / Odoo pos_caisse
