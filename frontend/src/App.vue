<template>
  <div class="app-container">
    <!-- HEADER & NAVBAR -->
    <header class="header-bar">
      <div class="brand-wrapper">
        <div class="brand-icon-box">
          🎬
        </div>
        <div class="brand-title-wrap">
          <h1 class="brand-title">
            Shorts Studio <span class="version-tag">IA v1.0</span>
          </h1>
          <p class="brand-subtitle">Automatisation de clips viraux 9:16 avec Face-Tracking & Sous-titres dynamiques</p>
        </div>
      </div>

      <div class="header-actions">
        <!-- Statut VPS -->
        <div class="status-pill">
          <span class="status-dot" :class="apiConnected ? 'online' : 'offline'"></span>
          <span>{{ apiConnected ? 'Serveur VPS En Ligne' : 'Connexion...' }}</span>
        </div>

        <!-- Bouton Cookies YouTube -->
        <button 
          @click="openCookiesModal"
          class="cookie-status-btn"
          :class="hasCookies ? 'active' : 'warning'"
          title="Gérer les cookies YouTube anti-bot"
        >
          <span>🍪</span>
          <span>{{ hasCookies ? 'Cookies : Actifs' : 'Cookies : Requis' }}</span>
        </button>

        <!-- Purge globale -->
        <button 
          v-if="shorts.length > 0"
          @click="purgeAll"
          class="btn btn-danger btn-sm"
          title="Supprime tous les shorts sur le VPS pour libérer le disque"
        >
          🗑️ Tout purger
        </button>
      </div>
    </header>

    <!-- FORMULAIRE DE CRÉATION DE SHORTS -->
    <section class="glass-panel hero-creation">
      <h2 class="section-title">
        ✨ Créer de nouveaux Shorts
      </h2>
      <p class="section-desc">
        Colle l'URL d'une vidéo YouTube (podcast, interview, divertissement). L'IA détecte les moments viraux et les découpe au format vertical 9:16.
      </p>

      <form @submit.prevent="submitAnalysis" class="creation-form">
        <!-- Champ URL -->
        <div class="input-group">
          <span class="input-icon">🔗</span>
          <input
            v-model="videoUrl"
            type="url"
            placeholder="https://www.youtube.com/watch?v=..."
            required
            class="url-input"
            :disabled="loading"
          />
          <button 
            type="button" 
            @click="pasteUrl"
            class="paste-button"
            title="Coller depuis le presse-papier"
          >
            📋 Coller
          </button>
        </div>

        <!-- Grille d'options -->
        <div class="options-grid">
          <!-- Mode de cadrage -->
          <div class="option-box">
            <span class="option-label">Format & Cadrage Vertical</span>
            <div class="segmented-control">
              <button
                type="button"
                @click="cropMode = 'crop'"
                :class="{ active: cropMode === 'crop' }"
                class="segmented-btn"
              >
                🎯 Plein écran (Face-Track)
              </button>
              <button
                type="button"
                @click="cropMode = 'blur'"
                :class="{ active: cropMode === 'blur' }"
                class="segmented-btn"
              >
                🌫️ Fond Flouté
              </button>
            </div>
          </div>

          <!-- Automatisation -->
          <div class="option-box">
            <label class="toggle-wrapper">
              <input 
                type="checkbox" 
                v-model="autoRender" 
                class="toggle-checkbox"
              />
              <div>
                <div class="toggle-text-main">Génération automatique</div>
                <div class="toggle-text-sub">Rendu immédiat des 3 meilleurs clips détectés</div>
              </div>
            </label>
          </div>
        </div>

        <!-- Bouton Soumettre -->
        <button
          type="submit"
          :disabled="loading || !videoUrl"
          class="submit-btn"
        >
          <span v-if="loading" class="spinner spinner-sm"></span>
          <span>{{ loading ? 'Lancement de l’analyse...' : '🚀 Détecter & Générer les Shorts' }}</span>
        </button>
      </form>
    </section>

    <!-- SUIVI DU TRAITEMENT EN COURS -->
    <section v-if="activeJob && activeJob.status !== 'completed'" class="glass-panel job-panel">
      <div class="job-header">
        <div class="job-left">
          <div class="job-spinner-box">
            <span class="spinner spinner-md"></span>
          </div>
          <div>
            <div class="job-badge-tag">Traitement IA en cours</div>
            <div class="job-step-title">{{ activeJob.step || 'Initialisation du pipeline...' }}</div>
            <div v-if="activeJob.metadata" class="job-meta-desc">
              {{ activeJob.metadata.title }} ({{ Math.floor(activeJob.metadata.duration / 60) }} min)
            </div>
          </div>
        </div>
        <div class="job-status-pill">
          {{ activeJob.status }}
        </div>
      </div>

      <!-- Erreur éventuelle -->
      <div v-if="activeJob.error" class="job-error-box">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="font-size: 1.1rem;">⚠️</span>
          <span>{{ activeJob.error }}</span>
        </div>
        <button 
          v-if="!hasCookies || activeJob.error.includes('cookies') || activeJob.error.includes('bot') || activeJob.error.includes('reloaded')"
          @click="openCookiesModal"
          class="btn btn-primary btn-sm"
          style="white-space: nowrap;"
        >
          🍪 Configurer les cookies
        </button>
      </div>
    </section>

    <!-- GALERIE DES SHORTS GÉNÉRÉS -->
    <section>
      <div class="gallery-header">
        <div>
          <h2 class="gallery-title">
            📥 Shorts Prêts au Téléchargement
            <span class="count-bubble">{{ shorts.length }}</span>
          </h2>
          <p class="gallery-sub">Visualisez vos clips 9:16 puis téléchargez-les avec purge automatique du VPS.</p>
        </div>
        <button @click="fetchShorts" class="btn btn-secondary btn-sm">
          🔄 Actualiser
        </button>
      </div>

      <!-- Aucun short -->
      <div v-if="shorts.length === 0" class="glass-panel empty-gallery">
        <div class="empty-icon">🎬</div>
        <h3 class="empty-title">Aucun Short généré pour le moment</h3>
        <p class="empty-desc">Colle une URL YouTube ci-dessus pour lancer la détection intelligente des moments viraux.</p>
      </div>

      <!-- Grille responsive des Shorts -->
      <div v-else class="shorts-grid">
        <article 
          v-for="short in shorts" 
          :key="short.id"
          class="short-card"
        >
          <!-- Conteneur Smartphone 9:16 STRICT -->
          <div class="video-frame-container">
            <video 
              :src="`/api/shorts/${short.id}/video`"
              controls
              playsinline
              preload="metadata"
              class="short-video-player"
            ></video>

            <!-- Badge Score Viral -->
            <div class="virality-badge">
              🔥 {{ short.clip.virality_score }}/10
            </div>

            <!-- Badge Durée & Format -->
            <div class="duration-badge">
              {{ Math.round(short.clip.end_time - short.clip.start_time) }}s • {{ short.crop_mode === 'crop' ? 'PLEIN ÉCRAN' : 'FLOU' }}
            </div>
          </div>

          <!-- Métadonnées & Accroche -->
          <div class="card-content">
            <div class="card-top">
              <!-- Titre -->
              <div class="card-title-row">
                <h3 class="card-title" :title="short.clip.title">
                  {{ short.clip.title }}
                </h3>
                <button 
                  @click="copyText(short.clip.title, 'Titre copié !')"
                  class="copy-icon-btn"
                  title="Copier le titre"
                >
                  📋
                </button>
              </div>

              <!-- Hook / Accroche IA -->
              <p class="card-hook" :title="short.clip.hook_summary">
                « {{ short.clip.hook_summary }} »
              </p>

              <!-- Hashtags -->
              <div class="hashtags-cluster" v-if="short.clip.hashtags && short.clip.hashtags.length">
                <span 
                  v-for="tag in short.clip.hashtags" 
                  :key="tag"
                  class="tag-pill"
                >
                  {{ tag }}
                </span>
              </div>
            </div>

            <!-- Actions Téléchargement & Purge -->
            <div class="card-actions-area">
              <!-- Télécharger & Purger (Recommandé) -->
              <button
                @click="downloadShort(short.id, true)"
                class="btn-purge-download"
                title="Télécharge la vidéo sur votre appareil et libère immédiatement le disque du VPS"
              >
                ⚡ Télécharger & Purger du VPS
              </button>

              <div class="actions-sub-row">
                <!-- Télécharger uniquement -->
                <button
                  @click="downloadShort(short.id, false)"
                  class="btn-save-vps"
                  title="Télécharger sans supprimer du serveur"
                >
                  💾 Garder sur VPS
                </button>
                <!-- Supprimer manuellement -->
                <button
                  @click="deleteShort(short.id)"
                  class="btn-delete-short"
                  title="Supprimer définitivement du VPS"
                >
                  🗑️
                </button>
              </div>

              <div class="file-size-info">
                Taille fichier : {{ short.file_size_mb }} Mo
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <!-- TOAST NOTIFICATION -->
    <div v-if="toastMessage" class="toast-container">
      <span style="color: #6ee7b7; font-size: 1.1rem;">✓</span>
      <span>{{ toastMessage }}</span>
    </div>

    <!-- MODAL CONFIGURATION COOKIES YOUTUBE -->
    <div v-if="showCookiesModal" class="modal-backdrop" @click.self="showCookiesModal = false">
      <div class="modal-dialog">
        <button 
          @click="showCookiesModal = false"
          class="modal-close-btn"
          title="Fermer"
        >
          ✕
        </button>

        <div class="modal-header">
          <div class="modal-icon-box">
            🍪
          </div>
          <div>
            <h3 class="modal-title">Cookies YouTube (Anti-Bot VPS)</h3>
            <p class="modal-desc">Authentification sécurisée requise par YouTube pour autoriser le téléchargement</p>
          </div>
        </div>

        <!-- Guide pas à pas -->
        <div class="guide-card">
          <div class="guide-card-title">
            <span>✨</span> Méthode infaillible (Anti-erreur 'The page needs to be reloaded') :
          </div>
          <ol class="guide-steps">
            <li>Ouvrez <a href="https://youtube.com" target="_blank" rel="noopener">youtube.com</a> connecté à votre compte.</li>
            <li>
              <strong>Étape clé :</strong> Dans ce même onglet, naviguez vers :
              <br/>
              <a href="https://www.youtube.com/robots.txt" target="_blank" rel="noopener">https://www.youtube.com/robots.txt</a>
              <div class="guide-tip">↳ Empêche YouTube de réinitialiser le jeton de session pendant l'export.</div>
            </li>
            <li>Cliquez sur l'extension <strong>Get cookies.txt LOCALLY</strong> puis sur <strong>Export</strong>.</li>
            <li>Déposez le fichier <code>cookies.txt</code> ci-dessous et validez.</li>
          </ol>
        </div>

        <!-- Résultat test session -->
        <div v-if="testResult" class="test-alert" :class="testResult.success ? 'success' : 'error'">
          <div style="font-weight: 700; display: flex; align-items: center; gap: 6px;">
            <span>{{ testResult.success ? '✓' : '⚠️' }}</span>
            <span>{{ testResult.success ? testResult.message : testResult.error }}</span>
          </div>
          <div v-if="testResult.hint" style="margin-top: 4px; font-size: 0.75rem; opacity: 0.9;">
            💡 {{ testResult.hint }}
          </div>
        </div>

        <!-- Dropzone -->
        <div 
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="handleFileDrop"
          class="dropzone"
          :class="{ active: dragOver }"
          @click="triggerFileInput"
        >
          <input type="file" ref="fileInput" @change="handleFileSelect" accept=".txt" style="display: none;" />
          <div class="dropzone-icon">📄</div>
          <div class="dropzone-label">Glissez votre fichier cookies.txt ici</div>
          <div class="dropzone-sub">ou cliquez pour sélectionner le fichier depuis votre ordinateur</div>
        </div>

        <!-- Textarea secours -->
        <div class="textarea-group">
          <label class="textarea-label">Ou collez le contenu texte brut :</label>
          <textarea 
            v-model="cookiesInputText" 
            rows="3" 
            placeholder="# Netscape HTTP Cookie File&#10;.youtube.com TRUE / FALSE 1750000000 VISITOR_INFO1_LIVE ..."
            class="cookies-textarea"
          ></textarea>
        </div>

        <!-- Footer Actions -->
        <div class="modal-footer">
          <div class="modal-footer-status">
            <span v-if="cookiesStatus.configured" style="color: #6ee7b7;">✓ Actifs sur le serveur ({{ Math.round(cookiesStatus.file_size_bytes / 1024) }} Ko)</span>
            <span v-else style="color: #fcd34d;">⚠️ Aucun cookie configuré</span>
          </div>
          <div class="modal-footer-actions">
            <button 
              @click="testCurrentCookies"
              :disabled="testingCookies"
              type="button" 
              class="btn btn-secondary btn-sm"
            >
              <span v-if="testingCookies" class="spinner spinner-sm"></span>
              <span>{{ testingCookies ? 'Test en cours...' : '🧪 Tester la connexion' }}</span>
            </button>
            <button 
              v-if="cookiesStatus.configured" 
              @click="removeCookies" 
              type="button" 
              class="btn btn-danger btn-sm"
            >
              Supprimer
            </button>
            <button 
              @click="saveCookies" 
              :disabled="savingCookies || !cookiesInputText.trim()" 
              type="button" 
              class="btn btn-primary btn-sm"
            >
              {{ savingCookies ? 'Enregistrement...' : 'Enregistrer les cookies' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const videoUrl = ref('')
const cropMode = ref('crop')
const autoRender = ref(true)
const loading = ref(false)
const apiConnected = ref(false)
const shorts = ref([])
const activeJob = ref(null)
const toastMessage = ref('')
const hasCookies = ref(false)
const showCookiesModal = ref(false)
const cookiesInputText = ref('')
const savingCookies = ref(false)
const dragOver = ref(false)
const fileInput = ref(null)
const cookiesStatus = ref({ configured: false, file_size_bytes: 0 })
const testResult = ref(null)
const testingCookies = ref(false)

let pollInterval = null

const showToast = (msg) => {
  toastMessage.value = msg
  setTimeout(() => {
    toastMessage.value = ''
  }, 3200)
}

const copyText = (text, successMsg) => {
  navigator.clipboard.writeText(text)
  showToast(successMsg)
}

const pasteUrl = async () => {
  try {
    const text = await navigator.clipboard.readText()
    if (text) videoUrl.value = text
  } catch {
    // Ignore clipboard read error
  }
}

// Vérifier l'état de l'API
const checkHealth = async () => {
  try {
    const res = await fetch('/api/health')
    if (res.ok) {
      const data = await res.json()
      apiConnected.value = true
      hasCookies.value = Boolean(data.has_cookies)
    }
  } catch {
    apiConnected.value = false
  }
}

// Récupérer le statut détaillé des cookies
const fetchCookiesStatus = async () => {
  try {
    const res = await fetch('/api/cookies')
    if (res.ok) {
      const data = await res.json()
      cookiesStatus.value = data
      hasCookies.value = Boolean(data.configured)
    }
  } catch (err) {
    console.error('Erreur chargement cookies status:', err)
  }
}

const openCookiesModal = () => {
  fetchCookiesStatus()
  showCookiesModal.value = true
}

const triggerFileInput = () => {
  if (fileInput.value) {
    fileInput.value.click()
  }
}

const handleFileSelect = (e) => {
  const file = e.target.files?.[0]
  if (file) readFileContent(file)
}

const handleFileDrop = (e) => {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) readFileContent(file)
}

const readFileContent = (file) => {
  const reader = new FileReader()
  reader.onload = (event) => {
    cookiesInputText.value = event.target?.result || ''
    showToast(`Fichier ${file.name} chargé (${Math.round(file.size / 1024)} Ko)`)
  }
  reader.readAsText(file)
}

const saveCookies = async () => {
  if (!cookiesInputText.value.trim()) return
  savingCookies.value = true
  testResult.value = null
  try {
    const res = await fetch('/api/cookies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: cookiesInputText.value })
    })
    if (res.ok) {
      showToast('Cookies YouTube enregistrés avec succès !')
      cookiesInputText.value = ''
      await fetchCookiesStatus()
      await testCurrentCookies()
    } else {
      const data = await res.json()
      showToast('Erreur : ' + (data.detail || 'Impossible d enregistrer'))
    }
  } catch {
    showToast('Erreur réseau lors de l enregistrement')
  } finally {
    savingCookies.value = false
  }
}

const testCurrentCookies = async () => {
  testingCookies.value = true
  testResult.value = null
  try {
    const res = await fetch('/api/cookies/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: videoUrl.value || undefined })
    })
    const data = await res.json()
    testResult.value = data
    if (data.success) {
      showToast('Session YouTube validée !')
    }
  } catch (err) {
    testResult.value = {
      success: false,
      error: 'Erreur lors du test de connexion : ' + err.message
    }
  } finally {
    testingCookies.value = false
  }
}

const removeCookies = async () => {
  if (!confirm('Supprimer les cookies YouTube du serveur ?')) return
  try {
    const res = await fetch('/api/cookies', { method: 'DELETE' })
    if (res.ok) {
      showToast('Cookies supprimés')
      await fetchCookiesStatus()
      cookiesInputText.value = ''
    }
  } catch {
    showToast('Erreur suppression cookies')
  }
}

// Récupérer la liste des shorts
const fetchShorts = async () => {
  try {
    const res = await fetch('/api/shorts')
    if (res.ok) {
      shorts.value = await res.json()
    }
  } catch (err) {
    console.error('Erreur chargement shorts:', err)
  }
}

// Lancer l'analyse
const submitAnalysis = async () => {
  if (!videoUrl.value) return
  loading.value = true

  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: videoUrl.value,
        crop_mode: cropMode.value,
        auto_render: autoRender.value
      })
    })

    if (!res.ok) throw new Error('Erreur lors du lancement')
    const data = await res.json()
    activeJob.value = { id: data.job_id, status: 'queued', step: 'Lancement du traitement...' }
    videoUrl.value = ''
    showToast('Analyse lancée avec succès !')
  } catch (err) {
    showToast('Erreur : ' + err.message)
  } finally {
    loading.value = false
  }
}

// Polling de l'état des jobs
const pollJobStatus = async () => {
  if (!activeJob.value || activeJob.value.status === 'completed' || activeJob.value.status === 'failed') {
    return
  }

  try {
    const res = await fetch(`/api/jobs/${activeJob.value.id}`)
    if (res.ok) {
      const job = await res.json()
      activeJob.value = job
      if (job.status === 'completed') {
        fetchShorts()
        showToast('Nouveau(x) Short(s) prêt(s) !')
      }
    }
  } catch (err) {
    console.error('Erreur polling:', err)
  }
}

// Télécharger un Short (avec ou sans suppression auto)
const downloadShort = (id, deleteAfter) => {
  const url = `/api/shorts/${id}/download?delete_after=${deleteAfter}`
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', `${id}.mp4`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)

  if (deleteAfter) {
    showToast('Téléchargement lancé & Short purgé du VPS')
    setTimeout(() => {
      fetchShorts()
    }, 1500)
  } else {
    showToast('Téléchargement lancé')
  }
}

// Supprimer manuellement un Short
const deleteShort = async (id) => {
  if (!confirm('Supprimer définitivement ce Short du serveur ?')) return
  try {
    const res = await fetch(`/api/shorts/${id}`, { method: 'DELETE' })
    if (res.ok) {
      showToast('Short supprimé')
      fetchShorts()
    }
  } catch (err) {
    showToast('Erreur suppression')
  }
}

// Purger tous les shorts
const purgeAll = async () => {
  if (!confirm('Êtes-vous sûr de vouloir supprimer TOUS les Shorts du VPS ?')) return
  try {
    const res = await fetch('/api/shorts/purge-all', { method: 'POST' })
    if (res.ok) {
      showToast('Espace disque libéré')
      fetchShorts()
    }
  } catch (err) {
    showToast('Erreur lors de la purge')
  }
}

onMounted(() => {
  checkHealth()
  fetchShorts()
  fetchCookiesStatus()
  pollInterval = setInterval(() => {
    pollJobStatus()
    checkHealth()
  }, 2500)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>
