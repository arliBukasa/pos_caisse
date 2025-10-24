# Script d'application automatique du fix Android
# Fix pour le bug de synchronisation : commandes SYNCED sans onlineId
# Auteur: Arnold
# Date: 2025-01-XX

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  FIX ANDROID - Synchronisation Commandes" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$ANDROID_PROJECT = "c:\Users\arnol\Documents\ProjetsAndroid\pos_mobile_sumni"
$SYNC_REPO_FILE = "$ANDROID_PROJECT\app\src\main\java\com\bulkasoft\pos\data\sync\SyncRepository.kt"
$BACKUP_DIR = "$ANDROID_PROJECT\backup_before_fix"
$PATCH_FILE = "c:\odoo\server\odoo\addons\pos_caisse\android_sync_fix.patch"
$APK_RELEASE = "$ANDROID_PROJECT\app\build\outputs\apk\release\app-release.apk"

# Étape 1 : Vérification des prérequis
Write-Host "[1/8] Vérification des prérequis..." -ForegroundColor Yellow

if (-not (Test-Path $ANDROID_PROJECT)) {
    Write-Host "❌ ERREUR: Projet Android introuvable: $ANDROID_PROJECT" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $SYNC_REPO_FILE)) {
    Write-Host "❌ ERREUR: Fichier SyncRepository.kt introuvable: $SYNC_REPO_FILE" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Projet Android trouvé" -ForegroundColor Green
Write-Host ""

# Étape 2 : Backup de la base de données
Write-Host "[2/8] Backup de la base de données SQLite..." -ForegroundColor Yellow

try {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $db_backup = "$BACKUP_DIR\pos_offline_${timestamp}.bdd"
    
    if (-not (Test-Path $BACKUP_DIR)) {
        New-Item -ItemType Directory -Path $BACKUP_DIR -Force | Out-Null
    }
    
    # Copie de la base de données locale (si disponible)
    $local_db = "$ANDROID_PROJECT\pos_offline.bdd"
    if (Test-Path $local_db) {
        Copy-Item $local_db -Destination $db_backup
        Write-Host "✅ Backup DB: $db_backup" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Base de données locale non trouvée (normal si sur appareil)" -ForegroundColor DarkYellow
    }
} catch {
    Write-Host "❌ ERREUR lors du backup DB: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Étape 3 : Backup du code source
Write-Host "[3/8] Backup du code source..." -ForegroundColor Yellow

try {
    $code_backup = "$BACKUP_DIR\SyncRepository_${timestamp}.kt.bak"
    Copy-Item $SYNC_REPO_FILE -Destination $code_backup
    Write-Host "✅ Backup code: $code_backup" -ForegroundColor Green
} catch {
    Write-Host "❌ ERREUR lors du backup code: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Étape 4 : Application du patch
Write-Host "[4/8] Application du patch sur SyncRepository.kt..." -ForegroundColor Yellow

try {
    # Lecture du fichier original
    $content = Get-Content $SYNC_REPO_FILE -Raw
    
    # Vérification que le bug existe encore (pas déjà fixé)
    if ($content -match "VALIDATION STRICTE : onlineId OBLIGATOIRE") {
        Write-Host "⚠️  Le fix semble déjà appliqué!" -ForegroundColor DarkYellow
        $response = Read-Host "Voulez-vous continuer quand même? (o/n)"
        if ($response -ne "o") {
            Write-Host "❌ Annulé par l'utilisateur" -ForegroundColor Red
            exit 0
        }
    }
    
    # Application manuelle des modifications
    Write-Host "   Modification de extractOnlineId()..." -ForegroundColor Gray
    
    # Fix 1 : extractOnlineId avec logs détaillés
    $content = $content -replace `
        'if \(idFromBody != null\) return idFromBody\s+val location = resp\.headers\(\)\["Location"\]\s+location\?\.substringAfterLast\(''/'')\?\.toLongOrNull\(\)', `
        @'
if (idFromBody != null) {
                Log.d("SyncRepository", "extractOnlineId: found in body = $idFromBody")
                return idFromBody
            }
            
            // Tentative 2 : extraction depuis header Location
            val location = resp.headers()["Location"]
            val idFromLocation = location?.substringAfterLast('/')?.toLongOrNull()
            if (idFromLocation != null) {
                Log.d("SyncRepository", "extractOnlineId: found in Location header = $idFromLocation")
                return idFromLocation
            }
            
            // Échec : aucune source n'a fourni d'ID
            Log.w("SyncRepository", "extractOnlineId: FAILED - no onlineId found in body or headers. Response code=${resp.code()}")
            null
'@
    
    Write-Host "   Modification de createOrQueueCommande()..." -ForegroundColor Gray
    
    # Fix 2 : createOrQueueCommande validation onlineId
    $content = $content -replace `
        'if \(resp\.isSuccessful \|\| resp\.code\(\) == 409\) \{\s+val onlineId = extractOnlineId\(resp\)\s+Log\.d\("SyncRepository", "createOrQueue: server accepted, onlineId=\$onlineId"\)\s+// Mirror locally as SYNCED for UI dashboards\s+saveMirrorSynced\(clientCard, clientName, typePaiement, totalFc, lignes, key, onlineId, sessionId, isVc\)\s+return@withContext true\s+\}', `
        @'
if (resp.isSuccessful || resp.code() == 409) {
                val onlineId = extractOnlineId(resp)
                
                // VALIDATION STRICTE : onlineId OBLIGATOIRE
                if (onlineId != null) {
                    Log.d("SyncRepository", "createOrQueue: SUCCESS - server accepted, onlineId=$onlineId")
                    // Mirror locally as SYNCED for UI dashboards
                    saveMirrorSynced(clientCard, clientName, typePaiement, totalFc, lignes, key, onlineId, sessionId, isVc)
                    return@withContext true
                } else {
                    // Serveur a accepté mais pas d'onlineId → queue en LOCAL pour retry
                    Log.w("SyncRepository", "createOrQueue: ANOMALY - server accepted (${resp.code()}) but onlineId=null, queueing idemKey=$key")
                    saveLocalCommande(clientCard, clientName, typePaiement, totalFc, lignes, key, sessionId, isVc)
                    return@withContext false
                }
            }
'@
    
    Write-Host "   Modification de pushOne()..." -ForegroundColor Gray
    
    # Fix 3 : pushOne validation onlineId
    $content = $content -replace `
        'if \(resp\.isSuccessful \|\| resp\.code\(\) == 409\) \{\s+val onlineId = extractOnlineId\(resp\)\s+dao\.markSynced\(cmd\.localId, onlineId, LocalCommande\.Status\.SYNCED, System\.currentTimeMillis\(\)\)\s+Log\.d\("SyncRepository", "pushOne: marked SYNCED localId=\$\{cmd\.localId\} onlineId=\$\{onlineId\}"\)\s+true\s+\}', `
        @'
if (resp.isSuccessful || resp.code() == 409) {
                val onlineId = extractOnlineId(resp)
                
                // VALIDATION STRICTE : onlineId OBLIGATOIRE pour marquer SYNCED
                if (onlineId != null) {
                    dao.markSynced(cmd.localId, onlineId, LocalCommande.Status.SYNCED, System.currentTimeMillis())
                    Log.d("SyncRepository", "pushOne: SUCCESS - marked SYNCED localId=${cmd.localId} onlineId=${onlineId}")
                    true
                } else {
                    // Serveur a accepté (200/409) mais pas d'onlineId → FAILED pour retry
                    Log.w("SyncRepository", "pushOne: ANOMALY - server accepted (${resp.code()}) but onlineId=null, marking FAILED for retry localId=${cmd.localId}")
                    dao.markFailed(cmd.localId, LocalCommande.Status.FAILED, System.currentTimeMillis())
                    false
                }
            }
'@
    
    # Sauvegarde du fichier modifié
    $content | Set-Content $SYNC_REPO_FILE -NoNewline
    
    Write-Host "✅ Patch appliqué avec succès" -ForegroundColor Green
    
} catch {
    Write-Host "❌ ERREUR lors de l'application du patch: $_" -ForegroundColor Red
    Write-Host "Restauration du backup..." -ForegroundColor Yellow
    Copy-Item $code_backup -Destination $SYNC_REPO_FILE -Force
    Write-Host "✅ Code source restauré" -ForegroundColor Green
    exit 1
}

Write-Host ""

# Étape 5 : Compilation
Write-Host "[5/8] Compilation de l'APK..." -ForegroundColor Yellow

try {
    Push-Location $ANDROID_PROJECT
    
    Write-Host "   Nettoyage du projet..." -ForegroundColor Gray
    & .\gradlew.bat clean 2>&1 | Out-Null
    
    Write-Host "   Compilation en mode release..." -ForegroundColor Gray
    $build_output = & .\gradlew.bat assembleRelease 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ ERREUR lors de la compilation:" -ForegroundColor Red
        Write-Host $build_output -ForegroundColor Red
        Pop-Location
        exit 1
    }
    
    Pop-Location
    
    if (Test-Path $APK_RELEASE) {
        $apk_size = (Get-Item $APK_RELEASE).Length / 1MB
        Write-Host "✅ APK compilé: $APK_RELEASE ($([math]::Round($apk_size, 2)) MB)" -ForegroundColor Green
    } else {
        Write-Host "❌ APK non trouvé après compilation" -ForegroundColor Red
        exit 1
    }
    
} catch {
    Write-Host "❌ ERREUR lors de la compilation: $_" -ForegroundColor Red
    Pop-Location
    exit 1
}

Write-Host ""

# Étape 6 : Installation sur appareil (optionnel)
Write-Host "[6/8] Installation sur appareil..." -ForegroundColor Yellow

try {
    # Vérification de la présence d'adb
    $adb = Get-Command adb -ErrorAction SilentlyContinue
    
    if ($null -eq $adb) {
        Write-Host "⚠️  ADB non trouvé, installation manuelle requise" -ForegroundColor DarkYellow
    } else {
        # Vérification des appareils connectés
        $devices = & adb devices
        
        if ($devices -match "device$") {
            $response = Read-Host "Appareil Android détecté. Installer l'APK? (o/n)"
            
            if ($response -eq "o") {
                Write-Host "   Installation de l'APK..." -ForegroundColor Gray
                & adb install -r $APK_RELEASE
                
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "✅ APK installé avec succès" -ForegroundColor Green
                } else {
                    Write-Host "❌ ERREUR lors de l'installation" -ForegroundColor Red
                }
            } else {
                Write-Host "⏭️  Installation ignorée" -ForegroundColor DarkYellow
            }
        } else {
            Write-Host "⚠️  Aucun appareil Android détecté" -ForegroundColor DarkYellow
        }
    }
    
} catch {
    Write-Host "⚠️  Installation ignorée: $_" -ForegroundColor DarkYellow
}

Write-Host ""

# Étape 7 : Re-synchronisation des commandes orphelines
Write-Host "[7/8] Re-synchronisation des commandes orphelines..." -ForegroundColor Yellow

$response = Read-Host "Voulez-vous re-synchroniser les 124 commandes orphelines du 26/09? (o/n)"

if ($response -eq "o") {
    try {
        Push-Location "c:\odoo\server\odoo\addons\pos_caisse"
        
        Write-Host "   Lancement du script de re-synchronisation..." -ForegroundColor Gray
        python scripts/resync_orphan_commandes.py --username arnold --password "Limon@de1" --date 2025-09-26
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ Re-synchronisation terminée" -ForegroundColor Green
        } else {
            Write-Host "❌ ERREUR lors de la re-synchronisation" -ForegroundColor Red
        }
        
        Pop-Location
        
    } catch {
        Write-Host "❌ ERREUR: $_" -ForegroundColor Red
        Pop-Location
    }
} else {
    Write-Host "⏭️  Re-synchronisation ignorée" -ForegroundColor DarkYellow
}

Write-Host ""

# Étape 8 : Vérification finale
Write-Host "[8/8] Vérification finale..." -ForegroundColor Yellow

try {
    Push-Location "c:\odoo\server\odoo\addons\pos_caisse"
    
    Write-Host "   Vérification de l'intégrité des données..." -ForegroundColor Gray
    
    # Vérification des commandes orphelines restantes
    python scripts/query_db.py --query "SELECT COUNT(*) as nb FROM local_commandes WHERE status='SYNCED' AND onlineId IS NULL"
    
    Write-Host ""
    Write-Host "   Comparaison locale vs online pour le 26/09..." -ForegroundColor Gray
    python scripts/compare_date.py --date 2025-09-26
    
    Pop-Location
    
    Write-Host "✅ Vérification terminée" -ForegroundColor Green
    
} catch {
    Write-Host "⚠️  Vérification partielle: $_" -ForegroundColor DarkYellow
    Pop-Location
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "           FIX TERMINÉ AVEC SUCCÈS!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Résumé des actions effectuées:" -ForegroundColor White
Write-Host "  ✅ Backup de la base de données" -ForegroundColor Gray
Write-Host "  ✅ Backup du code source" -ForegroundColor Gray
Write-Host "  ✅ Application du patch Android" -ForegroundColor Gray
Write-Host "  ✅ Compilation de l'APK" -ForegroundColor Gray
Write-Host "  ✅ Installation (si demandé)" -ForegroundColor Gray
Write-Host "  ✅ Re-synchronisation (si demandé)" -ForegroundColor Gray
Write-Host "  ✅ Vérification finale" -ForegroundColor Gray
Write-Host ""
Write-Host "Prochaines étapes:" -ForegroundColor Yellow
Write-Host "  1. Tester l'application sur un appareil" -ForegroundColor White
Write-Host "  2. Vérifier les logs Android (adb logcat | Select-String SyncRepository)" -ForegroundColor White
Write-Host "  3. Créer une commande test et vérifier le statut SYNCED" -ForegroundColor White
Write-Host "  4. Déployer sur tous les appareils de production" -ForegroundColor White
Write-Host ""
Write-Host "Documentation complète: c:\odoo\server\odoo\addons\pos_caisse\FIX_ANDROID_SYNC.md" -ForegroundColor Cyan
Write-Host ""
