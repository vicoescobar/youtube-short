<template>
  <div class="min-h-screen p-4 md:p-8 max-w-7xl mx-auto">
    <!-- HEADER -->
    <header class="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-8 pb-6 border-b border-white/10">
      <div>
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-600 to-cyan-500 flex items-center justify-center text-xl shadow-lg shadow-purple-500/30">
            🎬
          </div>
          <div>
            <h1 class="text-2xl md:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2">
              Shorts Studio <span class="text-xs px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">IA v1.0</span>
            </h1>
            <p class="text-sm text-slate-400">Automatisation de clips viraux 9:16 avec Face-Tracking & Sous-titres dynamiques</p>
          </div>
        </div>
      </div>

      <div class="flex items-center gap-3 w-full md:w-auto justify-between md:justify-end">
        <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs">
          <span class="w-2 h-2 rounded-full" :class="apiConnected ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'"></span>
          <span class="text-slate-300">{{ apiConnected ? 'Serveur VPS en ligne' : 'Connexion en cours...' }}</span>
        </div>

        <button 
          v-if="shorts.length > 0"
          @click="purgeAll"
          class="btn btn-danger text-xs px-3 py-1.5"
          title="Supprime tous les shorts sur le VPS pour libérer le disque"
        >
          🗑️ Tout purger
        </button>
      </div>
    </header>

    <!-- FORMULAIRE DE CRÉATION -->
    <section class="glass-panel p-6 md:p-8 mb-8 relative overflow-hidden">
      <div class="max-w-3xl">
        <h2 class="text-xl font-bold text-white mb-2 flex items-center gap-2">
          ✨ Créer de nouveaux Shorts
        </h2>
        <p class="text-sm text-slate-400 mb-6">
          Colle l'URL d'une vidéo YouTube (podcast, interview, divertissement). L'IA détecte les moments viraux et les découpe au format vertical 9:16.
        </p>

        <form @submit.prevent="submitAnalysis" class="space-y-4">
          <div class="relative">
            <input
              v-model="videoUrl"
              type="url"
              placeholder="https://www.youtube.com/watch?v=..."
              required
              class="input-field text-base pl-4 pr-24"
              :disabled="loading"
            />
            <button 
              type="button" 
              @click="pasteUrl"
              class="absolute right-2 top-2 px-3 py-1.5 text-xs text-slate-400 hover:text-white bg-white/5 hover:bg-white/10 rounded-md border border-white/10 transition"
            >
              Coller
            </button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <!-- Mode de cadrage -->
            <div class="p-4 rounded-xl bg-white/[0.03] border border-white/5">
              <label class="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
                Format Vertical
              </label>
              <div class="flex gap-2">
                <button
                  type="button"
                  @click="cropMode = 'crop'"
                  :class="cropMode === 'crop' ? 'btn-primary' : 'btn-secondary'"
                  class="btn text-xs flex-1"
                >
                  🎯 Plein écran (Face-Track)
                </button>
                <button
                  type="button"
                  @click="cropMode = 'blur'"
                  :class="cropMode === 'blur' ? 'btn-primary' : 'btn-secondary'"
                  class="btn text-xs flex-1"
                >
                  🌫️ Fond Flouté
                </button>
              </div>
            </div>

            <!-- Options auto -->
            <div class="p-4 rounded-xl bg-white/[0.03] border border-white/5 flex flex-col justify-center">
              <label class="flex items-center gap-3 cursor-pointer">
                <input 
                  type="checkbox" 
                  v-model="autoRender" 
                  class="w-4 h-4 rounded text-purple-600 focus:ring-purple-500 bg-slate-900 border-white/20"
                />
                <div>
                  <div class="text-sm font-semibold text-white">Génération automatique</div>
                  <div class="text-xs text-slate-400">Rendu immédiat des 3 meilleurs clips détectés</div>
                </div>
              </label>
            </div>
          </div>

          <button
            type="submit"
            :disabled="loading || !videoUrl"
            class="btn btn-primary w-full py-4 text-base font-bold flex items-center justify-center gap-2 mt-4"
          >
            <span v-if="loading" class="spinner inline-block w-5 h-5 border-2 border-white/20 border-t-white rounded-full"></span>
            <span>{{ loading ? 'Lancement de l’analyse...' : '🚀 Analyser et Générer les Shorts' }}</span>
          </button>
        </form>
      </div>
    </section>

    <!-- SUIVI DU JOB EN COURS -->
    <section v-if="activeJob && activeJob.status !== 'completed'" class="glass-panel p-6 mb-8 border-purple-500/40 bg-purple-950/20">
      <div class="flex items-center justify-between gap-4">
        <div class="flex items-center gap-4">
          <div class="w-10 h-10 rounded-full bg-purple-500/20 border border-purple-500/40 flex items-center justify-center text-purple-300">
            <span class="spinner inline-block w-5 h-5 border-2 border-purple-400/20 border-t-purple-400 rounded-full"></span>
          </div>
          <div>
            <div class="text-xs uppercase font-bold tracking-wider text-purple-400">Traitement en arrière-plan</div>
            <div class="text-base font-semibold text-white">{{ activeJob.step || 'Initialisation...' }}</div>
            <div v-if="activeJob.metadata" class="text-xs text-slate-400 mt-0.5">
              {{ activeJob.metadata.title }} ({{ Math.floor(activeJob.metadata.duration / 60) }}m)
            </div>
          </div>
        </div>
        <div class="text-xs px-3 py-1 rounded-full bg-purple-500/20 text-purple-300 font-mono">
          {{ activeJob.status }}
        </div>
      </div>
      <div v-if="activeJob.error" class="mt-4 p-3 rounded-lg bg-red-500/20 border border-red-500/30 text-red-300 text-sm">
        ❌ {{ activeJob.error }}
      </div>
    </section>

    <!-- GALERIE DES SHORTS GÉNÉRÉS -->
    <section>
      <div class="flex items-center justify-between mb-6">
        <div>
          <h2 class="text-xl font-bold text-white flex items-center gap-2">
            📥 Shorts Prêts au Téléchargement
            <span class="text-xs px-2.5 py-0.5 rounded-full bg-white/10 text-slate-300 font-mono">{{ shorts.length }}</span>
          </h2>
          <p class="text-xs text-slate-400">Les vidéos peuvent être téléchargées puis supprimées en un clic pour libérer l'espace disque du VPS.</p>
        </div>
        <button @click="fetchShorts" class="btn btn-secondary text-xs px-3 py-1.5 flex items-center gap-1.5">
          🔄 Actualiser
        </button>
      </div>

      <!-- Aucun short -->
      <div v-if="shorts.length === 0" class="glass-panel p-12 text-center text-slate-400">
        <div class="text-4xl mb-3">🎬</div>
        <h3 class="text-base font-semibold text-white mb-1">Aucun Short pour le moment</h3>
        <p class="text-xs text-slate-500 max-w-sm mx-auto">Colle une URL YouTube ci-dessus pour lancer la détection des meilleurs moments viraux.</p>
      </div>

      <!-- Grille des shorts -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <article 
          v-for="short in shorts" 
          :key="short.id"
          class="glass-panel overflow-hidden flex flex-col transition hover:border-purple-500/30"
        >
          <!-- Lecteur Vidéo Vertical 9:16 -->
          <div class="relative bg-black aspect-[9/16] w-full max-h-[460px] flex items-center justify-center overflow-hidden">
            <video 
              :src="`/api/shorts/${short.id}/video`"
              controls
              playsinline
              preload="metadata"
              class="w-full h-full object-contain"
            ></video>
            <!-- Badge score viral -->
            <div class="absolute top-3 right-3 badge badge-purple shadow-lg">
              🔥 {{ short.clip.virality_score }}/10
            </div>
            <!-- Badge durée -->
            <div class="absolute bottom-3 left-3 px-2 py-0.5 rounded bg-black/70 backdrop-blur-md text-white text-[11px] font-mono">
              {{ Math.round(short.clip.end_time - short.clip.start_time) }}s • {{ short.crop_mode.toUpperCase() }}
            </div>
          </div>

          <!-- Contenu & Métadonnées -->
          <div class="p-5 flex-1 flex flex-col justify-between space-y-4">
            <div>
              <!-- Titre du Short -->
              <div class="flex items-start justify-between gap-2 mb-2">
                <h3 class="font-bold text-white text-base leading-snug">
                  {{ short.clip.title }}
                </h3>
                <button 
                  @click="copyText(short.clip.title, 'Titre copié !')"
                  class="text-xs p-1 text-slate-400 hover:text-purple-300 transition"
                  title="Copier le titre"
                >
                  📋
                </button>
              </div>

              <!-- Accroche / Hook -->
              <p class="text-xs text-slate-400 line-clamp-2 mb-3 italic">
                « {{ short.clip.hook_summary }} »
              </p>

              <!-- Tags -->
              <div class="flex flex-wrap gap-1.5 mb-3">
                <span 
                  v-for="tag in short.clip.hashtags" 
                  :key="tag"
                  class="text-[11px] px-2 py-0.5 rounded bg-white/5 text-purple-300 border border-white/5"
                >
                  {{ tag }}
                </span>
              </div>
            </div>

            <!-- Actions de téléchargement et suppression -->
            <div class="pt-4 border-t border-white/10 space-y-2">
              <!-- Télécharger & Supprimer (Recommandé pour VPS) -->
              <button
                @click="downloadShort(short.id, true)"
                class="btn btn-success w-full text-xs font-bold py-2.5"
                title="Télécharge la vidéo et libère immédiatement l'espace disque sur le VPS"
              >
                ⚡ Télécharger & Purger du VPS
              </button>

              <div class="flex gap-2">
                <!-- Télécharger uniquement -->
                <button
                  @click="downloadShort(short.id, false)"
                  class="btn btn-secondary flex-1 text-xs py-2"
                >
                  💾 Garder sur VPS
                </button>
                <!-- Supprimer manuellement -->
                <button
                  @click="deleteShort(short.id)"
                  class="btn btn-danger text-xs px-3 py-2"
                  title="Supprimer définitivement"
                >
                  🗑️
                </button>
              </div>

              <div class="text-[11px] text-slate-500 text-center pt-1">
                Taille : {{ short.file_size_mb }} Mo
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <!-- TOAST NOTIFICATION -->
    <div 
      v-if="toastMessage" 
      class="fixed bottom-6 right-6 z-50 px-4 py-3 rounded-xl bg-purple-900/90 text-white border border-purple-500/40 shadow-2xl backdrop-blur-md text-sm font-semibold flex items-center gap-2 animate-bounce"
    >
      <span>✓</span> {{ toastMessage }}
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

let pollInterval = null

const showToast = (msg) => {
  toastMessage.value = msg
  setTimeout(() => {
    toastMessage.value = ''
  }, 3000)
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
      apiConnected.value = true
    }
  } catch {
    apiConnected.value = false
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
  pollInterval = setInterval(() => {
    pollJobStatus()
    checkHealth()
  }, 2500)
})

onUnmounted(() => {
  if (pollInterval) clearInterval(pollInterval)
})
</script>

<style scoped>
/* Scoped adjustments */
</style>
