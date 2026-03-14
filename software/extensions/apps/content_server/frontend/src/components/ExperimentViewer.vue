<template>
    <div class="experiment-viewer" v-if="experiment">
        <div class="viewer-header">
            <div class="nav-section">
                <button v-if="experiment.folderPath && experiment.folderPath.length > 0" class="back-btn" @click="goBack">
                    &larr; Back
                </button>
                <router-link v-else to="/" class="back-btn">&larr; Home</router-link>

                <div class="breadcrumb">
                    <router-link to="/" class="breadcrumb-item">Home</router-link>
                    <template v-for="(crumb, index) in experiment.folderPath" :key="crumb.id">
                        <span class="breadcrumb-sep">/</span>
                        <router-link :to="`/folder/${crumb.id}`" class="breadcrumb-item">
                            {{ crumb.name }}
                        </router-link>
                    </template>
                    <span class="breadcrumb-sep">/</span>
                    <span class="breadcrumb-item current">{{ experiment.title }}</span>
                </div>
            </div>
            <div class="header-info">
                <div class="title-row">
                    <h1 class="item-title">{{ experiment.title }}</h1>
                    <span class="item-type-badge" :class="experimentType">
                        <svg v-if="experimentType === 'synchronized'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <path d="M12 6v6l4 2"/>
                        </svg>
                        <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                        </svg>
                        {{ experimentType === 'synchronized' ? 'Synchronized Playback' : 'Video Collection' }}
                    </span>
                </div>
                <p class="item-description">{{ experiment.description }}</p>
                <div class="header-extras">
                    <DocRefBadge :item="experiment" />
                    <button v-if="experiment.additionalInfo" class="info-btn" @click="showInfo = true">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
                        More Information
                    </button>
                </div>
                <InfoPanel :visible="showInfo" :content="experiment.additionalInfo || ''" @close="showInfo = false" />
            </div>
        </div>

        <!-- Loading overlay for synchronized videos -->
        <div v-if="experimentType === 'synchronized' && !allVideosReady" class="buffering-overlay">
            <div class="buffering-content">
                <div class="buffering-spinner"></div>
                <div class="buffering-text">Buffering videos... {{ readyVideos }}/{{ experiment?.videos?.length || 0 }}</div>
            </div>
        </div>

        <!-- Normal grid view - Synchronized type -->
        <div v-if="maximizedVideo === null && experimentType === 'synchronized'" class="video-grid" :class="[gridClass, { 'videos-loading': !allVideosReady }]">
            <div
                v-for="(video, index) in experiment.videos"
                :key="index"
                class="video-container"
            >
                <div class="video-header">
                    <span class="video-label">{{ video.name }}</span>
                    <div class="video-header-actions">
                        <button class="fullscreen-btn" @click="requestFullscreen(index, 'grid')" title="Fullscreen">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
                            </svg>
                        </button>
                        <button class="maximize-btn" @click="maximizeVideo(index)" title="Maximize">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <video
                    ref="videoRefs"
                    :src="`/videos/${video.file}`"
                    @loadedmetadata="onVideoLoaded(index)"
                    @canplaythrough.once="onVideoCanPlayThrough(index)"
                    @timeupdate="onTimeUpdate(index)"
                    @ended="onVideoEnded"
                    @error="onVideoError(index, $event)"
                    @waiting="onVideoWaiting(index)"
                    @canplay="onVideoCanPlay(index)"
                    preload="auto"
                    playsinline
                    muted
                ></video>
                <VideoOverlay
                    :current-time="currentTime"
                    :overlays="video.overlays"
                    :overlay-style="video.overlayStyle"
                />
                <VideoOverlay
                    v-if="experiment.overlays && experiment.overlays.length"
                    :current-time="currentTime"
                    :overlays="experiment.overlays"
                    :overlay-style="experiment.overlayStyle"
                />
                <div v-if="videoErrors[index]" class="video-error">
                    Video not found: {{ video.file }}
                </div>
            </div>
        </div>

        <!-- Normal grid view - Collection type (each video has own controls) -->
        <div v-else-if="maximizedVideo === null && experimentType === 'collection'" class="video-grid collection-grid" :class="gridClass">
            <div
                v-for="(video, index) in experiment.videos"
                :key="index"
                class="video-container collection-video"
            >
                <div class="video-header">
                    <span class="video-label">{{ video.name }}</span>
                    <div class="video-header-actions">
                        <button class="fullscreen-btn" @click="requestFullscreen(index, 'grid')" title="Fullscreen">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
                            </svg>
                        </button>
                        <button class="maximize-btn" @click="maximizeVideo(index)" title="Maximize">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <video
                    ref="collectionVideoRefs"
                    :src="`/videos/${video.file}`"
                    @loadedmetadata="onCollectionVideoLoaded(index)"
                    @loadeddata="onCollectionVideoLoadedData(index)"
                    @timeupdate="onCollectionTimeUpdate(index)"
                    @ended="onCollectionVideoEnded(index)"
                    @error="onVideoError(index, $event)"
                    preload="auto"
                    playsinline
                ></video>
                <VideoOverlay
                    :current-time="collectionTimes[index] || 0"
                    :overlays="video.overlays"
                    :overlay-style="video.overlayStyle"
                />
                <!-- Center play button overlay -->
                <div class="video-center-play" :class="{ playing: collectionPlaying[index] }" @click="toggleCollectionVideo(index)">
                    <div class="center-play-btn">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="currentColor">
                            <polygon points="5 3 19 12 5 21 5 3"/>
                        </svg>
                    </div>
                </div>
                <div v-if="videoErrors[index]" class="video-error">
                    Video not found: {{ video.file }}
                </div>
                <!-- Individual video controls -->
                <div class="video-controls">
                    <button class="video-play-btn" @click="toggleCollectionVideo(index)">
                        <span v-if="collectionPlaying[index]" class="pause-icon-small">&#10074;&#10074;</span>
                        <span v-else class="play-icon-small">&#9654;</span>
                    </button>
                    <div class="video-timeline" @mousedown="startCollectionDrag(index, $event)">
                        <div class="video-timeline-progress" :style="{ width: getCollectionProgress(index) + '%' }"></div>
                    </div>
                    <span class="video-time">{{ formatTime(collectionTimes[index] || 0) }}</span>
                </div>
            </div>
        </div>

        <!-- Maximized view (Zoom-style spotlight) - Synchronized type -->
        <div v-else-if="experimentType === 'synchronized'" class="spotlight-view" :class="{ 'videos-loading': !allSpotlightVideosReady }">
            <!-- Loading overlay for spotlight videos -->
            <div v-if="!allSpotlightVideosReady" class="buffering-overlay spotlight-buffering">
                <div class="buffering-content">
                    <div class="buffering-spinner"></div>
                    <div class="buffering-text">Buffering... {{ spotlightReadyVideos }}/{{ (experiment?.videos?.length || 0) > 1 ? (experiment?.videos?.length || 0) * 2 : (experiment?.videos?.length || 0) }}</div>
                </div>
            </div>
            <div class="spotlight-main">
                <!-- Render all videos, show only the selected one -->
                <div
                    v-for="(video, index) in experiment.videos"
                    :key="index"
                    class="video-container spotlight-video"
                    :class="{ 'spotlight-hidden': index !== maximizedVideo }"
                >
                    <div class="video-header">
                        <span class="video-label">{{ video.name }}</span>
                        <div class="video-header-actions">
                            <button class="fullscreen-btn" @click="requestFullscreen(index, 'spotlight')" title="Fullscreen">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
                                </svg>
                            </button>
                            <button class="minimize-btn" @click="minimizeVideo" title="Minimize">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                    <video
                        ref="spotlightVideoRefs"
                        :src="`/videos/${video.file}`"
                        @loadedmetadata="onSpotlightVideoLoaded(index)"
                        @canplaythrough.once="onSpotlightCanPlayThrough(index)"
                        @timeupdate="onSpotlightTimeUpdate(index)"
                        @waiting="onVideoWaiting(index)"
                        @canplay="onVideoCanPlay(index)"
                        preload="auto"
                        playsinline
                        muted
                    ></video>
                    <VideoOverlay
                        :current-time="currentTime"
                        :overlays="video.overlays"
                        :overlay-style="video.overlayStyle"
                    />
                    <VideoOverlay
                        v-if="experiment.overlays && experiment.overlays.length"
                        :current-time="currentTime"
                        :overlays="experiment.overlays"
                        :overlay-style="experiment.overlayStyle"
                    />
                </div>
            </div>
            <div class="spotlight-sidebar" v-if="experiment.videos.length > 1">
                <div
                    v-for="(video, index) in experiment.videos"
                    :key="index"
                    class="sidebar-video"
                    :class="{ active: index === maximizedVideo }"
                    @click="switchSpotlight(index)"
                >
                    <div class="sidebar-label">{{ video.name }}</div>
                    <video
                        ref="sidebarVideoRefs"
                        :src="`/videos/${video.file}`"
                        @loadedmetadata="onSidebarVideoLoaded(index)"
                        @canplaythrough.once="onSidebarCanPlayThrough(index)"
                        preload="auto"
                        playsinline
                        muted
                    ></video>
                </div>
            </div>
        </div>

        <!-- Maximized view - Collection type (controls only current video) -->
        <div v-else class="spotlight-view collection-spotlight">
            <div class="spotlight-main">
                <div class="video-container spotlight-video">
                    <div class="video-header">
                        <span class="video-label">{{ experiment.videos[maximizedVideo].name }}</span>
                        <div class="video-header-actions">
                            <button class="fullscreen-btn" @click="requestFullscreen(maximizedVideo, 'spotlight')" title="Fullscreen">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>
                                </svg>
                            </button>
                            <button class="minimize-btn" @click="minimizeVideo" title="Minimize">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                    <video
                        ref="collectionSpotlightRef"
                        :src="`/videos/${experiment.videos[maximizedVideo].file}`"
                        @loadedmetadata="onCollectionSpotlightLoaded"
                        @timeupdate="onCollectionSpotlightTimeUpdate"
                        @ended="onCollectionSpotlightEnded"
                        @waiting="onCollectionSpotlightWaiting"
                        @canplay="onCollectionSpotlightCanPlay"
                        preload="auto"
                        playsinline
                    ></video>
                    <VideoOverlay
                        :current-time="collectionSpotlightTime"
                        :overlays="experiment.videos[maximizedVideo]?.overlays"
                        :overlay-style="experiment.videos[maximizedVideo]?.overlayStyle"
                    />
                    <!-- Center play button overlay -->
                    <div class="video-center-play" :class="{ playing: collectionSpotlightPlaying }" @click="toggleCollectionSpotlight">
                        <div class="center-play-btn">
                            <svg width="64" height="64" viewBox="0 0 24 24" fill="currentColor">
                                <polygon points="5 3 19 12 5 21 5 3"/>
                            </svg>
                        </div>
                    </div>
                </div>
            </div>
            <div class="spotlight-sidebar" v-if="experiment.videos.length > 1">
                <div
                    v-for="(video, index) in experiment.videos"
                    :key="index"
                    class="sidebar-video"
                    :class="{ active: index === maximizedVideo }"
                    @click="switchCollectionVideo(index)"
                >
                    <div class="sidebar-label">{{ video.name }}</div>
                    <video
                        :src="`/videos/${video.file}`"
                        preload="auto"
                        playsinline
                        muted
                    ></video>
                </div>
            </div>
        </div>

        <!-- Controls for synchronized type -->
        <div v-if="experimentType === 'synchronized'" class="controls-container">
            <div class="timeline-controls">
                <button class="play-btn" :class="{ loading: !isReadyToPlay }" @click="togglePlayPause" :disabled="!isReadyToPlay">
                    <span v-if="!isReadyToPlay" class="loading-spinner"></span>
                    <span v-else-if="isPlaying" class="pause-icon">&#10074;&#10074;</span>
                    <span v-else class="play-icon">&#9654;</span>
                </button>

                <div class="timeline-wrapper">
                    <div class="time-display">
                        {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
                        <span v-if="isBuffering && isPlaying" class="buffering-badge">Buffering...</span>
                    </div>

                    <div class="timeline-with-markers">
                        <div class="timeline" @mousedown="startSyncDrag">
                            <div class="timeline-progress" :style="{ width: progressPercent + '%' }"></div>
                            <div class="timeline-handle" :style="{ left: progressPercent + '%' }"></div>

                            <div
                                v-for="(marker, index) in experiment.markers"
                                :key="index"
                                class="timeline-marker"
                                :class="{ highlighted: hoveredMarkerIndex === index }"
                                :style="{ left: getMarkerPosition(marker.time) + '%' }"
                                @click.stop="seekTo(marker.time)"
                            ></div>
                        </div>

                        <div class="markers-labels" v-if="experiment.markers && experiment.markers.length > 0">
                            <button
                                v-for="(marker, index) in experiment.markers"
                                :key="index"
                                class="marker-label"
                                :class="{ active: isNearMarker(marker.time), highlighted: hoveredMarkerIndex === index }"
                                :style="{ left: getMarkerPosition(marker.time) + '%' }"
                                @click="seekTo(marker.time)"
                                @mouseenter="hoveredMarkerIndex = index"
                                @mouseleave="hoveredMarkerIndex = null"
                            >
                                {{ marker.label }}
                            </button>
                        </div>
                    </div>
                </div>

                <div class="playback-controls">
                    <div class="volume-controls">
                        <button class="mute-btn" @click="toggleMute" :title="isMuted ? 'Unmute' : 'Mute'">
                            <svg v-if="isMuted || volume === 0" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <line x1="23" y1="9" x2="17" y2="15"/>
                                <line x1="17" y1="9" x2="23" y2="15"/>
                            </svg>
                            <svg v-else-if="volume < 0.5" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
                            </svg>
                            <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
                            </svg>
                        </button>
                        <input
                            type="range"
                            class="volume-slider"
                            min="0"
                            max="1"
                            step="0.05"
                            :value="volume"
                            @input="setVolume"
                        >
                    </div>
                    <div class="speed-dropdown" :class="{ open: speedDropdownOpen }">
                        <button class="speed-btn" @click="toggleSpeedDropdown">
                            {{ playbackSpeed }}x
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M6 9l6 6 6-6"/>
                            </svg>
                        </button>
                        <div class="speed-options" v-if="speedDropdownOpen">
                            <button
                                v-for="speed in speeds"
                                :key="speed"
                                class="speed-option"
                                :class="{ active: speed === playbackSpeed }"
                                @click="setSpeed(speed)"
                            >
                                {{ speed }}x
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Controls for collection type (only in maximized view) -->
        <div v-if="experimentType === 'collection' && maximizedVideo !== null" class="controls-container collection-controls">
            <div class="timeline-controls">
                <button class="play-btn collection" @click="toggleCollectionSpotlight">
                    <span v-if="collectionSpotlightPlaying" class="pause-icon">&#10074;&#10074;</span>
                    <span v-else class="play-icon">&#9654;</span>
                </button>

                <div class="timeline-wrapper">
                    <div class="time-display">
                        {{ formatTime(collectionSpotlightTime) }} / {{ formatTime(collectionSpotlightDuration) }}
                    </div>

                    <div class="timeline collection" @mousedown="startSpotlightDrag">
                        <div class="timeline-progress" :style="{ width: collectionSpotlightProgress + '%' }"></div>
                        <div class="timeline-handle" :style="{ left: collectionSpotlightProgress + '%' }"></div>
                    </div>
                </div>

                <div class="playback-controls">
                    <div class="volume-controls">
                        <button class="mute-btn" @click="toggleMute" :title="isMuted ? 'Unmute' : 'Mute'">
                            <svg v-if="isMuted || volume === 0" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <line x1="23" y1="9" x2="17" y2="15"/>
                                <line x1="17" y1="9" x2="23" y2="15"/>
                            </svg>
                            <svg v-else-if="volume < 0.5" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
                            </svg>
                            <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>
                            </svg>
                        </button>
                        <input
                            type="range"
                            class="volume-slider"
                            min="0"
                            max="1"
                            step="0.05"
                            :value="volume"
                            @input="setVolume"
                        >
                    </div>
                    <div class="speed-dropdown" :class="{ open: speedDropdownOpen }">
                        <button class="speed-btn" @click="toggleSpeedDropdown">
                            {{ playbackSpeed }}x
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M6 9l6 6 6-6"/>
                            </svg>
                        </button>
                        <div class="speed-options" v-if="speedDropdownOpen">
                            <button
                                v-for="speed in speeds"
                                :key="speed"
                                class="speed-option"
                                :class="{ active: speed === playbackSpeed }"
                                @click="setCollectionSpeed(speed)"
                            >
                                {{ speed }}x
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div v-else class="loading">
        Loading experiment...
    </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import DocRefBadge from './DocRefBadge.vue'
import InfoPanel from './InfoPanel.vue'
import VideoOverlay from './VideoOverlay.vue'

const showInfo = ref(false)

const props = defineProps({
    id: String
})

const router = useRouter()

const experiment = ref(null)
const videoRefs = ref([])
const spotlightVideoRefs = ref([])
const sidebarVideoRefs = ref([])
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const playbackSpeed = ref(1)
const videoErrors = ref({})
const loadedVideos = ref(0)
const readyVideos = ref(0)
const spotlightReadyVideos = ref(0)
const maximizedVideo = ref(null)
const speedDropdownOpen = ref(false)
const isMuted = ref(false)
const volume = ref(1)
const hoveredMarkerIndex = ref(null)

// Collection type specific state
const collectionVideoRefs = ref([])
const collectionPlaying = ref({})
const collectionTimes = ref({})
const collectionDurations = ref({})
const collectionSpotlightRef = ref(null)
const collectionSpotlightPlaying = ref(false)
const collectionSpotlightTime = ref(0)
const collectionSpotlightDuration = ref(0)

// Dragging state for timeline scrubbing
const isDragging = ref(false)
const wasPlayingBeforeDrag = ref(false)

// Sync interval for keeping videos aligned
let syncInterval = null
const SYNC_THRESHOLD = 0.15 // seconds - resync if drift exceeds this
const SYNC_COOLDOWN = 500 // ms - minimum time between resyncs per video
const lastSyncTime = {} // track last sync time per video index
const videosBuffering = ref({}) // track which videos are buffering
const draggingCollectionIndex = ref(null)
const collectionWasPlayingBeforeDrag = ref(false)
const isDraggingSpotlight = ref(false)
const spotlightWasPlayingBeforeDrag = ref(false)

const speeds = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2]

const experimentType = computed(() => {
    return experiment.value?.type || 'synchronized'
})

const allVideosReady = computed(() => {
    if (!experiment.value?.videos) return false
    const totalVideos = experiment.value.videos.length
    return readyVideos.value >= totalVideos
})

const allSpotlightVideosReady = computed(() => {
    if (!experiment.value?.videos || maximizedVideo.value === null) return false
    const videoCount = experiment.value.videos.length
    // Sidebar only renders when more than 1 video
    const totalVideos = videoCount > 1 ? videoCount * 2 : videoCount
    return spotlightReadyVideos.value >= totalVideos
})

// Combined ready state for current view mode
const isReadyToPlay = computed(() => {
    if (maximizedVideo.value !== null) {
        return allSpotlightVideosReady.value
    }
    return allVideosReady.value
})

const gridClass = computed(() => {
    const count = experiment.value?.videos?.length || 0
    if (count <= 1) return 'grid-1'
    if (count === 2) return 'grid-2'
    if (count === 3) return 'grid-3'
    if (count === 4) return 'grid-4'
    if (count <= 6) return 'grid-6'
    return 'grid-auto'
})

const progressPercent = computed(() => {
    if (duration.value === 0) return 0
    return (currentTime.value / duration.value) * 100
})

const collectionSpotlightProgress = computed(() => {
    if (collectionSpotlightDuration.value === 0) return 0
    return (collectionSpotlightTime.value / collectionSpotlightDuration.value) * 100
})

const isBuffering = computed(() => {
    return Object.values(videosBuffering.value).some(v => v)
})

function goBack() {
    if (experiment.value?.folderPath && experiment.value.folderPath.length > 0) {
        const parent = experiment.value.folderPath[experiment.value.folderPath.length - 1]
        router.push(`/folder/${parent.id}`)
    } else {
        router.push('/')
    }
}

function formatTime(seconds) {
    if (isNaN(seconds)) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
}

function getMarkerPosition(time) {
    if (duration.value === 0) return 0
    return (time / duration.value) * 100
}

function isNearMarker(time) {
    return Math.abs(currentTime.value - time) < 0.5
}

function onVideoLoaded(index) {
    loadedVideos.value++
    const video = videoRefs.value[index]
    if (video) {
        if (video.duration > duration.value) {
            duration.value = video.duration
        }
        // Volume will be applied when playing (videos start muted for iOS compatibility)
        video.volume = volume.value
    }
}

function onVideoCanPlayThrough(index) {
    readyVideos.value++
}

function onVideoWaiting(index) {
    // Video is buffering - track it and pause all if playing
    videosBuffering.value[index] = true
    if (isPlaying.value && Object.values(videosBuffering.value).some(v => v)) {
        // At least one video is buffering - pause all to let them catch up
        const videos = getAllVideos()
        videos.forEach(video => {
            if (video && !video.paused) {
                video.pause()
            }
        })
    }
}

function onVideoCanPlay(index) {
    // Video finished buffering
    videosBuffering.value[index] = false

    // If we were playing and all videos are now ready, resume
    if (isPlaying.value && !Object.values(videosBuffering.value).some(v => v)) {
        const videos = getAllVideos()
        const masterTime = videos[0]?.currentTime || currentTime.value

        // Sync all videos to master time before resuming
        videos.forEach((video, idx) => {
            if (video) {
                video.currentTime = masterTime
            }
        })

        // Resume playback
        Promise.all(videos.map(video => {
            if (video) {
                return video.play().catch(e => console.log('Resume play error:', e))
            }
            return Promise.resolve()
        }))
    }
}

function onVideoError(index, event) {
    videoErrors.value[index] = true
}

function onTimeUpdate(index) {
    // Only track time from video 0 (master) to prevent playhead jitter
    if (index !== 0) return
    const video = videoRefs.value[0]
    if (video) {
        currentTime.value = video.currentTime
    }
}

function onSpotlightVideoLoaded(index) {
    const video = spotlightVideoRefs.value[index]
    if (video) {
        if (video.duration > duration.value) {
            duration.value = video.duration
        }
        // Volume will be applied when playing (videos start muted for iOS compatibility)
        video.volume = volume.value
    }
}

function onSpotlightCanPlayThrough(index) {
    spotlightReadyVideos.value++
}

function onSidebarCanPlayThrough(index) {
    spotlightReadyVideos.value++
}

function onSpotlightTimeUpdate(index) {
    // Only track time from video 0 (master) to prevent playhead jitter
    if (index !== 0) return
    const video = spotlightVideoRefs.value[0]
    if (video) {
        currentTime.value = video.currentTime
    }
}

function switchSpotlight(index) {
    // Instant switch - just change which video is visible
    maximizedVideo.value = index
}

function onSidebarVideoLoaded(index) {
    const video = sidebarVideoRefs.value[index]
    if (video) {
        video.muted = true // Sidebar videos are always muted
    }
}

function onVideoEnded() {
    stopSyncInterval()
    isPlaying.value = false
}

function getAllVideos() {
    if (maximizedVideo.value !== null) {
        // In spotlight mode, get both main spotlight videos and sidebar videos
        const videos = []
        if (spotlightVideoRefs.value) {
            spotlightVideoRefs.value.forEach(v => { if (v) videos.push(v) })
        }
        if (sidebarVideoRefs.value) {
            sidebarVideoRefs.value.forEach(v => { if (v) videos.push(v) })
        }
        return videos
    }
    return videoRefs.value.filter(v => v)
}

function togglePlayPause() {
    if (isPlaying.value) {
        pauseAll()
    } else {
        playAll()
    }
}

function syncVideos() {
    // Sync all videos to master (video 0)
    const videos = getAllVideos()
    if (!videos || videos.length < 2) return

    const master = videos[0]
    if (!master || master.paused) return

    // If any video is buffering, don't try to sync - let buffering detection handle it
    if (Object.values(videosBuffering.value).some(v => v)) return

    const masterTime = master.currentTime
    const now = Date.now()

    for (let i = 1; i < videos.length; i++) {
        const video = videos[i]
        if (!video) continue

        // Skip if this video is buffering (readyState < 3 means not enough data)
        if (video.readyState < 3) continue

        const drift = Math.abs(video.currentTime - masterTime)
        if (drift > SYNC_THRESHOLD) {
            // Check cooldown to prevent rapid re-syncing
            const lastSync = lastSyncTime[i] || 0
            if (now - lastSync > SYNC_COOLDOWN) {
                // Use playbackRate adjustment for small drifts to avoid jumps
                if (drift < 0.5) {
                    // Gently speed up or slow down to catch up
                    const targetRate = video.currentTime < masterTime ? 1.05 : 0.95
                    video.playbackRate = playbackSpeed.value * targetRate
                    // Reset to normal after a short delay
                    setTimeout(() => {
                        if (video) video.playbackRate = playbackSpeed.value
                    }, 200)
                } else {
                    // Large drift - need to hard sync
                    video.currentTime = masterTime
                }
                lastSyncTime[i] = now
            }
        }
    }
}

function startSyncInterval() {
    stopSyncInterval()
    // Clear cooldown tracking
    Object.keys(lastSyncTime).forEach(k => delete lastSyncTime[k])
    // Check sync every 250ms for smoother playback
    syncInterval = setInterval(syncVideos, 250)
}

function stopSyncInterval() {
    if (syncInterval) {
        clearInterval(syncInterval)
        syncInterval = null
    }
}

function playAll() {
    const videos = getAllVideos()
    if (!videos || videos.length === 0) return

    // Reset buffering state
    Object.keys(videosBuffering.value).forEach(k => delete videosBuffering.value[k])

    // If video ended (at or near the end), restart from beginning
    let targetTime = currentTime.value
    if (duration.value > 0 && currentTime.value >= duration.value - 0.1) {
        targetTime = 0
        currentTime.value = 0
    }

    // For iOS compatibility: mute all videos except the first one
    // iOS only allows one video with audio, but multiple muted videos can play
    videos.forEach((video, index) => {
        if (video) {
            video.currentTime = targetTime
            video.playbackRate = playbackSpeed.value
            // First video keeps user's mute preference, others are force-muted for iOS
            if (index === 0) {
                video.muted = isMuted.value
                video.volume = volume.value
            } else {
                video.muted = true
            }
        }
    })

    // Start all videos using Promise.all for proper synchronization
    const playPromises = videos.map(video => {
        if (video) {
            return video.play().catch(e => {
                console.log('Play error:', e)
                return null
            })
        }
        return Promise.resolve()
    })

    Promise.all(playPromises).then(() => {
        isPlaying.value = true
        startSyncInterval()
    })
}

function pauseAll() {
    stopSyncInterval()
    const videos = getAllVideos()
    videos.forEach(video => {
        if (video) video.pause()
    })
    isPlaying.value = false
}

function seekTo(time) {
    const videos = getAllVideos()
    videos.forEach(video => {
        if (video) {
            video.currentTime = time
            // Force frame render if paused
            if (!isPlaying.value) {
                video.pause()
            }
        }
    })
    currentTime.value = time
}

function seekToPosition(event) {
    const timeline = event.currentTarget
    const rect = timeline.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * duration.value
    seekTo(time)
}

// Synchronized player drag handlers
let syncTimelineEl = null
let syncSeeking = false
let syncPendingTime = null

function performSyncSeek(time) {
    if (syncSeeking) {
        // Store pending time, will be applied when current seek completes
        syncPendingTime = time
        currentTime.value = time  // Update UI immediately
        return
    }

    const videos = getAllVideos()
    if (videos.length === 0) return

    syncSeeking = true
    syncPendingTime = null
    currentTime.value = time

    // Use first video as reference for seeked event
    const refVideo = videos[0]

    const onSeeked = () => {
        refVideo.removeEventListener('seeked', onSeeked)
        syncSeeking = false

        // If there's a pending seek, execute it
        if (syncPendingTime !== null && isDragging.value) {
            const pendingTime = syncPendingTime
            syncPendingTime = null
            performSyncSeek(pendingTime)
        }
    }

    refVideo.addEventListener('seeked', onSeeked)

    // Seek all videos
    videos.forEach(video => {
        if (video) {
            video.currentTime = time
        }
    })
}

function startSyncDrag(event) {
    event.preventDefault()
    isDragging.value = true
    wasPlayingBeforeDrag.value = isPlaying.value
    syncTimelineEl = event.currentTarget
    syncSeeking = false
    syncPendingTime = null

    // Pause all videos during scrub
    const videos = getAllVideos()
    videos.forEach(video => {
        if (video) {
            video.pause()
        }
    })
    isPlaying.value = false

    // Seek to initial position
    const rect = syncTimelineEl.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * duration.value
    performSyncSeek(time)

    // Add window listeners
    window.addEventListener('mousemove', onSyncDrag)
    window.addEventListener('mouseup', stopSyncDrag)
}

function onSyncDrag(event) {
    if (!isDragging.value || !syncTimelineEl) return

    const rect = syncTimelineEl.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * duration.value

    performSyncSeek(time)
}

function stopSyncDrag() {
    if (!isDragging.value) return

    isDragging.value = false
    window.removeEventListener('mousemove', onSyncDrag)
    window.removeEventListener('mouseup', stopSyncDrag)
    syncTimelineEl = null

    // Final seek to pending time if any
    if (syncPendingTime !== null) {
        const videos = getAllVideos()
        videos.forEach(video => {
            if (video) video.currentTime = syncPendingTime
        })
        currentTime.value = syncPendingTime
    }
    syncSeeking = false
    syncPendingTime = null

    // Pause if wasn't playing before drag
    if (!wasPlayingBeforeDrag.value) {
        pauseAll()
    } else {
        playAll()
    }
}

function toggleSpeedDropdown() {
    speedDropdownOpen.value = !speedDropdownOpen.value
}

function setSpeed(speed) {
    playbackSpeed.value = speed
    speedDropdownOpen.value = false

    const videos = getAllVideos()
    videos.forEach(video => {
        if (video) video.playbackRate = speed
    })
}

function maximizeVideo(index) {
    const wasPlaying = isPlaying.value
    const time = currentTime.value

    pauseAll()
    spotlightReadyVideos.value = 0  // Reset ready state for spotlight videos
    maximizedVideo.value = index

    nextTick(() => {
        // Sync all spotlight videos to current time
        // Only first video can have audio (iOS compatibility)
        const mainVideos = spotlightVideoRefs.value.filter(v => v)
        mainVideos.forEach((video, idx) => {
            video.currentTime = time
            video.volume = volume.value
            video.playbackRate = playbackSpeed.value
            // Only first video respects mute setting, others muted for iOS
            video.muted = idx === 0 ? isMuted.value : true
        })

        // Sync sidebar videos (always muted)
        const sidebarVideos = sidebarVideoRefs.value.filter(v => v)
        sidebarVideos.forEach(video => {
            video.currentTime = time
            video.muted = true
            video.playbackRate = playbackSpeed.value
        })

        currentTime.value = time

        if (wasPlaying) {
            setTimeout(() => {
                // Use Promise.all for proper iOS synchronization
                const allVideos = [...mainVideos, ...sidebarVideos]
                Promise.all(allVideos.map(video =>
                    video.play().catch(e => console.log('Play error:', e))
                )).then(() => {
                    isPlaying.value = true
                    startSyncInterval()
                })
            }, 50)
        }
    })
}

function minimizeVideo() {
    if (experimentType.value === 'collection') {
        // For collection, just go back to grid view
        if (collectionSpotlightRef.value) {
            collectionSpotlightRef.value.pause()
        }
        collectionSpotlightPlaying.value = false
        maximizedVideo.value = null
        return
    }

    const wasPlaying = isPlaying.value
    const time = currentTime.value

    pauseAll()
    maximizedVideo.value = null

    nextTick(() => {
        seekTo(time)
        if (wasPlaying) {
            setTimeout(() => playAll(), 100)
        }
    })
}

function requestFullscreen(index, viewType) {
    let video = null
    if (viewType === 'grid') {
        video = experimentType.value === 'collection'
            ? collectionVideoRefs.value?.[index]
            : videoRefs.value?.[index]
    } else if (viewType === 'spotlight') {
        video = experimentType.value === 'collection'
            ? collectionSpotlightRef.value
            : spotlightVideoRefs.value?.[index]
    }
    if (video) {
        // Fullscreen the container (.video-container) so overlays remain visible
        const container = video.closest('.video-container') || video.closest('.spotlight-video-area')
        const el = container || video
        if (el.requestFullscreen) el.requestFullscreen()
        else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen()
        else if (video.webkitEnterFullScreen) video.webkitEnterFullScreen()
    }
}

// ==================== Collection Type Functions ====================

function onCollectionVideoLoaded(index) {
    const videos = collectionVideoRefs.value
    if (videos && videos[index]) {
        collectionDurations.value[index] = videos[index].duration
        collectionTimes.value[index] = 0
        collectionPlaying.value[index] = false
        // Apply saved volume settings
        videos[index].muted = isMuted.value
        videos[index].volume = volume.value
    }
}

function onCollectionVideoLoadedData(index) {
    // Force render the first frame as a thumbnail
    // This fixes the issue where videos show as black on iOS until played
    const videos = collectionVideoRefs.value
    if (videos && videos[index]) {
        // Seek to very start to ensure first frame is rendered
        videos[index].currentTime = 0.001
    }
}

function onCollectionTimeUpdate(index) {
    const videos = collectionVideoRefs.value
    if (videos && videos[index]) {
        collectionTimes.value[index] = videos[index].currentTime
    }
}

function onCollectionVideoEnded(index) {
    collectionPlaying.value[index] = false
}

function toggleCollectionVideo(index) {
    const videos = collectionVideoRefs.value
    if (!videos || !videos[index]) return

    const video = videos[index]
    if (collectionPlaying.value[index]) {
        video.pause()
        collectionPlaying.value[index] = false
    } else {
        // If video ended, restart from beginning
        const dur = collectionDurations.value[index] || 0
        const time = collectionTimes.value[index] || 0
        if (dur > 0 && time >= dur - 0.1) {
            video.currentTime = 0
            collectionTimes.value[index] = 0
        }
        video.playbackRate = playbackSpeed.value
        video.play().catch(e => console.log('Play error:', e))
        collectionPlaying.value[index] = true
    }
}

function seekCollectionVideo(index, event) {
    const videos = collectionVideoRefs.value
    if (!videos || !videos[index]) return

    const timeline = event.currentTarget
    const rect = timeline.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * (collectionDurations.value[index] || 0)

    videos[index].currentTime = time
    collectionTimes.value[index] = time
}

// Collection grid drag handlers
let collectionTimelineEl = null
let collectionSeeking = false
let collectionPendingTime = null

function performCollectionSeek(index, time) {
    const videos = collectionVideoRefs.value
    if (!videos || !videos[index]) return

    if (collectionSeeking) {
        // Store pending time, will be applied when current seek completes
        collectionPendingTime = time
        collectionTimes.value[index] = time  // Update UI immediately
        return
    }

    collectionSeeking = true
    collectionPendingTime = null
    collectionTimes.value[index] = time

    const video = videos[index]

    const onSeeked = () => {
        video.removeEventListener('seeked', onSeeked)
        collectionSeeking = false

        // If there's a pending seek, execute it
        if (collectionPendingTime !== null && draggingCollectionIndex.value !== null) {
            const pendingTime = collectionPendingTime
            collectionPendingTime = null
            performCollectionSeek(index, pendingTime)
        }
    }

    video.addEventListener('seeked', onSeeked)
    video.currentTime = time
}

function startCollectionDrag(index, event) {
    event.preventDefault()
    draggingCollectionIndex.value = index
    collectionTimelineEl = event.currentTarget
    collectionSeeking = false
    collectionPendingTime = null

    const videos = collectionVideoRefs.value
    if (!videos || !videos[index]) return

    collectionWasPlayingBeforeDrag.value = collectionPlaying.value[index] || false

    // Pause video during scrub
    videos[index].pause()
    collectionPlaying.value[index] = false

    // Seek to initial position
    const rect = collectionTimelineEl.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * (collectionDurations.value[index] || 0)
    performCollectionSeek(index, time)

    window.addEventListener('mousemove', onCollectionDrag)
    window.addEventListener('mouseup', stopCollectionDrag)
}

function onCollectionDrag(event) {
    if (draggingCollectionIndex.value === null || !collectionTimelineEl) return

    const index = draggingCollectionIndex.value
    const rect = collectionTimelineEl.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * (collectionDurations.value[index] || 0)

    performCollectionSeek(index, time)
}

function stopCollectionDrag() {
    if (draggingCollectionIndex.value === null) return

    const index = draggingCollectionIndex.value
    const videos = collectionVideoRefs.value

    // Final seek to pending time if any
    if (collectionPendingTime !== null && videos && videos[index]) {
        videos[index].currentTime = collectionPendingTime
        collectionTimes.value[index] = collectionPendingTime
    }
    collectionSeeking = false
    collectionPendingTime = null

    // Pause if wasn't playing before drag
    if (!collectionWasPlayingBeforeDrag.value && videos && videos[index]) {
        videos[index].pause()
        collectionPlaying.value[index] = false
    } else if (videos && videos[index]) {
        videos[index].play().catch(() => {})
        collectionPlaying.value[index] = true
    }

    draggingCollectionIndex.value = null
    collectionTimelineEl = null
    window.removeEventListener('mousemove', onCollectionDrag)
    window.removeEventListener('mouseup', stopCollectionDrag)
}

function getCollectionProgress(index) {
    const dur = collectionDurations.value[index] || 0
    if (dur === 0) return 0
    return ((collectionTimes.value[index] || 0) / dur) * 100
}

function switchCollectionVideo(index) {
    // Stop current spotlight video
    if (collectionSpotlightRef.value) {
        collectionSpotlightRef.value.pause()
    }
    collectionSpotlightPlaying.value = false
    collectionSpotlightTime.value = 0

    // Switch to new video
    maximizedVideo.value = index

    nextTick(() => {
        if (collectionSpotlightRef.value) {
            collectionSpotlightRef.value.currentTime = 0
            collectionSpotlightDuration.value = collectionSpotlightRef.value.duration || 0
        }
    })
}

function onCollectionSpotlightLoaded() {
    if (collectionSpotlightRef.value) {
        collectionSpotlightDuration.value = collectionSpotlightRef.value.duration
        // Apply saved volume settings
        collectionSpotlightRef.value.muted = isMuted.value
        collectionSpotlightRef.value.volume = volume.value
    }
}

function onCollectionSpotlightTimeUpdate() {
    if (collectionSpotlightRef.value) {
        collectionSpotlightTime.value = collectionSpotlightRef.value.currentTime
    }
}

function onCollectionSpotlightEnded() {
    collectionSpotlightPlaying.value = false
}

function onCollectionSpotlightWaiting() {
    // Video is buffering - show loading state but keep playing state
    // The video element will automatically resume when buffer is ready
}

function onCollectionSpotlightCanPlay() {
    // Video finished buffering and is ready to play
    // If we should be playing, ensure playback continues
    if (collectionSpotlightPlaying.value && collectionSpotlightRef.value?.paused) {
        collectionSpotlightRef.value.play().catch(e => console.log('Resume play error:', e))
    }
}

function toggleCollectionSpotlight() {
    if (!collectionSpotlightRef.value) return

    if (collectionSpotlightPlaying.value) {
        collectionSpotlightRef.value.pause()
        collectionSpotlightPlaying.value = false
    } else {
        // If video ended, restart from beginning
        if (collectionSpotlightDuration.value > 0 && collectionSpotlightTime.value >= collectionSpotlightDuration.value - 0.1) {
            collectionSpotlightRef.value.currentTime = 0
            collectionSpotlightTime.value = 0
        }
        collectionSpotlightRef.value.playbackRate = playbackSpeed.value
        collectionSpotlightRef.value.play().catch(e => console.log('Play error:', e))
        collectionSpotlightPlaying.value = true
    }
}

function seekCollectionSpotlight(event) {
    if (!collectionSpotlightRef.value) return

    const timeline = event.currentTarget
    const rect = timeline.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * collectionSpotlightDuration.value

    collectionSpotlightRef.value.currentTime = time
    // Force frame render if paused
    if (!collectionSpotlightPlaying.value) {
        collectionSpotlightRef.value.pause()
    }
    collectionSpotlightTime.value = time
}

// Collection spotlight drag handlers
let spotlightTimelineEl = null
let spotlightSeeking = false
let spotlightPendingTime = null

function performSpotlightSeek(time) {
    if (!collectionSpotlightRef.value) return

    if (spotlightSeeking) {
        // Store pending time, will be applied when current seek completes
        spotlightPendingTime = time
        collectionSpotlightTime.value = time  // Update UI immediately
        return
    }

    spotlightSeeking = true
    spotlightPendingTime = null
    collectionSpotlightTime.value = time

    const video = collectionSpotlightRef.value

    const onSeeked = () => {
        video.removeEventListener('seeked', onSeeked)
        spotlightSeeking = false

        // If there's a pending seek, execute it
        if (spotlightPendingTime !== null && isDraggingSpotlight.value) {
            const pendingTime = spotlightPendingTime
            spotlightPendingTime = null
            performSpotlightSeek(pendingTime)
        }
    }

    video.addEventListener('seeked', onSeeked)
    video.currentTime = time
}

function startSpotlightDrag(event) {
    event.preventDefault()
    isDraggingSpotlight.value = true
    spotlightTimelineEl = event.currentTarget
    spotlightWasPlayingBeforeDrag.value = collectionSpotlightPlaying.value
    spotlightSeeking = false
    spotlightPendingTime = null

    if (!collectionSpotlightRef.value) return

    // Pause video during scrub
    collectionSpotlightRef.value.pause()
    collectionSpotlightPlaying.value = false

    // Seek to initial position
    const rect = spotlightTimelineEl.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * collectionSpotlightDuration.value
    performSpotlightSeek(time)

    window.addEventListener('mousemove', onSpotlightDrag)
    window.addEventListener('mouseup', stopSpotlightDrag)
}

function onSpotlightDrag(event) {
    if (!isDraggingSpotlight.value || !spotlightTimelineEl || !collectionSpotlightRef.value) return

    const rect = spotlightTimelineEl.getBoundingClientRect()
    const percent = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width))
    const time = percent * collectionSpotlightDuration.value

    performSpotlightSeek(time)
}

function stopSpotlightDrag() {
    if (!isDraggingSpotlight.value) return

    // Final seek to pending time if any
    if (spotlightPendingTime !== null && collectionSpotlightRef.value) {
        collectionSpotlightRef.value.currentTime = spotlightPendingTime
        collectionSpotlightTime.value = spotlightPendingTime
    }
    spotlightSeeking = false
    spotlightPendingTime = null

    // Pause if wasn't playing before drag
    if (!spotlightWasPlayingBeforeDrag.value && collectionSpotlightRef.value) {
        collectionSpotlightRef.value.pause()
        collectionSpotlightPlaying.value = false
    } else if (collectionSpotlightRef.value) {
        collectionSpotlightRef.value.play().catch(() => {})
        collectionSpotlightPlaying.value = true
    }

    isDraggingSpotlight.value = false
    spotlightTimelineEl = null
    window.removeEventListener('mousemove', onSpotlightDrag)
    window.removeEventListener('mouseup', stopSpotlightDrag)
}

function setCollectionSpeed(speed) {
    playbackSpeed.value = speed
    speedDropdownOpen.value = false

    if (collectionSpotlightRef.value) {
        collectionSpotlightRef.value.playbackRate = speed
    }

    // Also update any playing collection videos in grid
    const videos = collectionVideoRefs.value
    if (videos) {
        videos.forEach(video => {
            if (video) video.playbackRate = speed
        })
    }
}

// ==================== Volume Functions ====================

function loadVolumeSettings() {
    const savedMuted = localStorage.getItem('videoMuted')
    const savedVolume = localStorage.getItem('videoVolume')
    if (savedMuted !== null) {
        isMuted.value = savedMuted === 'true'
    }
    if (savedVolume !== null) {
        volume.value = parseFloat(savedVolume)
    }
}

function saveVolumeSettings() {
    localStorage.setItem('videoMuted', isMuted.value.toString())
    localStorage.setItem('videoVolume', volume.value.toString())
}

function toggleMute() {
    isMuted.value = !isMuted.value
    applyVolumeToAllVideos()
    saveVolumeSettings()
}

function setVolume(event) {
    volume.value = parseFloat(event.target.value)
    if (volume.value > 0 && isMuted.value) {
        isMuted.value = false
    }
    applyVolumeToAllVideos()
    saveVolumeSettings()
}

function applyVolumeToAllVideos() {
    // Apply to synchronized videos (grid mode)
    // Only first video can have audio (iOS compatibility), others stay muted
    if (videoRefs.value) {
        videoRefs.value.forEach((video, index) => {
            if (video) {
                video.volume = volume.value
                // Only first video respects mute setting, others stay muted for iOS
                if (index === 0) {
                    video.muted = isMuted.value
                }
            }
        })
    }

    // Apply to spotlight videos (maximized mode)
    if (spotlightVideoRefs.value) {
        spotlightVideoRefs.value.forEach((video, index) => {
            if (video) {
                video.volume = volume.value
                if (index === 0) {
                    video.muted = isMuted.value
                }
            }
        })
    }

    // Apply to collection videos (each plays independently, so all can have audio)
    if (collectionVideoRefs.value) {
        collectionVideoRefs.value.forEach(video => {
            if (video) {
                video.muted = isMuted.value
                video.volume = volume.value
            }
        })
    }

    // Apply to collection spotlight
    if (collectionSpotlightRef.value) {
        collectionSpotlightRef.value.muted = isMuted.value
        collectionSpotlightRef.value.volume = volume.value
    }
}

// Close speed dropdown when clicking outside
function handleClickOutside(event) {
    if (!event.target.closest('.speed-dropdown')) {
        speedDropdownOpen.value = false
    }
}

// Keyboard shortcuts
function handleKeydown(event) {
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA' || event.target.tagName === 'SELECT' || event.target.isContentEditable) return

    if (event.code === 'Space') {
        event.preventDefault()
        if (experimentType.value === 'collection') {
            if (maximizedVideo.value !== null) {
                toggleCollectionSpotlight()
            }
            // In grid view for collection, space does nothing (use individual buttons)
        } else if (isReadyToPlay.value) {
            togglePlayPause()
        }
    } else if (event.code === 'ArrowLeft') {
        if (experimentType.value === 'collection' && maximizedVideo.value !== null) {
            const newTime = Math.max(0, collectionSpotlightTime.value - 5)
            if (collectionSpotlightRef.value) {
                collectionSpotlightRef.value.currentTime = newTime
                collectionSpotlightTime.value = newTime
            }
        } else if (experimentType.value === 'synchronized') {
            seekTo(Math.max(0, currentTime.value - 5))
        }
    } else if (event.code === 'ArrowRight') {
        if (experimentType.value === 'collection' && maximizedVideo.value !== null) {
            const newTime = Math.min(collectionSpotlightDuration.value, collectionSpotlightTime.value + 5)
            if (collectionSpotlightRef.value) {
                collectionSpotlightRef.value.currentTime = newTime
                collectionSpotlightTime.value = newTime
            }
        } else if (experimentType.value === 'synchronized') {
            seekTo(Math.min(duration.value, currentTime.value + 5))
        }
    } else if (event.code === 'Escape' && maximizedVideo.value !== null) {
        minimizeVideo()
    }
}

async function loadExperiment() {
    // Reset state
    experiment.value = null
    isPlaying.value = false
    currentTime.value = 0
    duration.value = 0
    videoErrors.value = {}
    loadedVideos.value = 0
    readyVideos.value = 0
    spotlightReadyVideos.value = 0
    maximizedVideo.value = null
    collectionPlaying.value = {}
    collectionTimes.value = {}
    collectionDurations.value = {}
    collectionSpotlightPlaying.value = false
    collectionSpotlightTime.value = 0
    collectionSpotlightDuration.value = 0

    try {
        const response = await fetch(`/api/experiments/${props.id}`)
        experiment.value = await response.json()

        // For collection type, default to maximized view with first video
        if (experiment.value?.type === 'collection' && experiment.value?.videos?.length > 0) {
            maximizedVideo.value = 0
        }
    } catch (error) {
        console.error('Failed to load experiment:', error)
    }
}

// Watch for id changes (when navigating between experiments)
watch(() => props.id, () => {
    loadExperiment()
})

onMounted(async () => {
    // Load saved volume settings
    loadVolumeSettings()

    await loadExperiment()

    window.addEventListener('keydown', handleKeydown)
    window.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
    window.removeEventListener('keydown', handleKeydown)
    window.removeEventListener('click', handleClickOutside)
    // Clean up any drag listeners
    window.removeEventListener('mousemove', onSyncDrag)
    window.removeEventListener('mouseup', stopSyncDrag)
    window.removeEventListener('mousemove', onCollectionDrag)
    window.removeEventListener('mouseup', stopCollectionDrag)
    window.removeEventListener('mousemove', onSpotlightDrag)
    window.removeEventListener('mouseup', stopSpotlightDrag)
    stopSyncInterval()
    pauseAll()
})
</script>

<style scoped>
.experiment-viewer {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: hidden;
    position: relative;
}

.viewer-header {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-bottom: 10px;
    flex-shrink: 0;
}

.nav-section {
    display: flex;
    align-items: center;
    gap: 8px;
}

.breadcrumb {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    flex-wrap: wrap;
}

.breadcrumb-sep {
    color: var(--border-hover);
}

.back-btn {
    color: var(--text-primary);
    text-decoration: none;
    font-size: 13px;
    padding: 5px 12px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 6px;
    transition: all 0.2s;
    flex-shrink: 0;
    cursor: pointer;
}

.back-btn:hover {
    background: var(--border);
    border-color: var(--border-hover);
}

.breadcrumb-item {
    color: var(--text-muted);
    text-decoration: none;
    padding: 4px 10px;
    background: var(--bg-elevated);
    border-radius: 6px;
    transition: all 0.2s;
}

.breadcrumb-item:hover:not(.current) {
    background: var(--border);
    color: var(--text-primary);
}

.breadcrumb-item.current {
    color: var(--text-primary);
    background: var(--border-light);
}

.title-row {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
}

.item-title {
    font-size: 20px;
    font-weight: 600;
    margin: 0;
}

.item-type-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 500;
    padding: 4px 10px;
    border-radius: 6px;
}

.item-type-badge.synchronized {
    background: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    border: 1px solid rgba(59, 130, 246, 0.3);
}

.item-type-badge.collection {
    background: rgba(245, 158, 11, 0.15);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.3);
}

.item-description {
    color: var(--text-muted);
    font-size: 13px;
    margin-top: 4px;
}

/* Normal Grid View */
.video-grid {
    flex: 1;
    display: grid;
    gap: 12px;
    min-height: 0;
    overflow: hidden;
}

.grid-1 { grid-template-columns: 1fr; }
.grid-2 { grid-template-columns: repeat(2, 1fr); }
.grid-3 { grid-template-columns: repeat(3, 1fr); }
.grid-4 { grid-template-columns: repeat(2, 1fr); grid-template-rows: repeat(2, 1fr); }
.grid-6 { grid-template-columns: repeat(3, 1fr); grid-template-rows: repeat(2, 1fr); }
.grid-auto { grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); }

.video-container {
    position: relative;
    background: var(--code-bg);
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.video-container:fullscreen,
.spotlight-video-area:fullscreen {
    background: #000;
}

.video-container video {
    flex: 1;
    width: 100%;
    height: 100%;
    object-fit: contain;
}

.video-header {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    background: linear-gradient(to bottom, rgba(0,0,0,0.7) 0%, transparent 100%);
    z-index: 10;
}

.video-label {
    font-size: 13px;
    font-weight: 500;
    background: rgba(255, 255, 255, 0.1);
    padding: 6px 12px;
    border-radius: 6px;
}

.video-header-actions {
    display: flex;
    gap: 4px;
    align-items: center;
}

.fullscreen-btn {
    background: rgba(0, 0, 0, 0.6);
    border: none;
    color: white;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0.7;
    transition: opacity 0.2s;
}

.fullscreen-btn:hover {
    opacity: 1;
}

.maximize-btn, .minimize-btn {
    background: rgba(255,255,255,0.1);
    border: none;
    color: white;
    padding: 6px;
    border-radius: 6px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s;
}

.maximize-btn:hover, .minimize-btn:hover {
    background: rgba(255,255,255,0.2);
}

.video-error {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-elevated);
    color: var(--text-faint);
    font-size: 14px;
}

/* Spotlight View (Maximized) */
.spotlight-view {
    flex: 1;
    display: flex;
    gap: 12px;
    min-height: 0;
    overflow: hidden;
    position: relative;
}

.spotlight-buffering {
    border-radius: 12px;
}

.spotlight-main {
    flex: 1;
    min-width: 0;
    position: relative;
}

.spotlight-video {
    height: 100%;
}

.spotlight-video video {
    height: 100%;
}

.spotlight-video.spotlight-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
    pointer-events: none;
}

.spotlight-sidebar {
    width: 200px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    overflow-y: auto;
}

.sidebar-video {
    position: relative;
    background: var(--code-bg);
    border-radius: 8px;
    overflow: hidden;
    cursor: pointer;
    border: 2px solid transparent;
    transition: border-color 0.2s;
}

.sidebar-video:hover {
    border-color: var(--border-hover);
}

.sidebar-video.active {
    border-color: #3b82f6;
}

.sidebar-video video {
    width: 100%;
    height: auto;
    display: block;
}

.sidebar-label {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 6px 8px;
    background: linear-gradient(to top, rgba(0,0,0,0.8) 0%, transparent 100%);
    font-size: 11px;
    font-weight: 500;
}

/* Controls */
.controls-container {
    background: var(--code-bg);
    border-radius: 10px;
    padding: 10px 16px;
    margin-top: 8px;
    flex-shrink: 0;
}

.timeline-controls {
    display: flex;
    align-items: flex-start;
    gap: 14px;
}

.play-btn {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border: none;
    color: white;
    font-size: 13px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.2s, box-shadow 0.2s;
    flex-shrink: 0;
    margin-top: 9px;
}

.play-btn:hover {
    transform: scale(1.08);
    box-shadow: 0 3px 14px rgba(59, 130, 246, 0.4);
}

.play-icon { margin-left: 2px; }
.pause-icon { letter-spacing: 2px; font-size: 11px; }

.timeline-wrapper {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 5px;
}

.time-display {
    font-size: 12px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
    display: flex;
    align-items: center;
    gap: 8px;
}

.buffering-badge {
    font-size: 11px;
    color: #f59e0b;
    background: rgba(245, 158, 11, 0.15);
    padding: 2px 8px;
    border-radius: 4px;
    animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

.timeline-with-markers {
    position: relative;
}

.timeline {
    position: relative;
    height: 8px;
    background: var(--border);
    border-radius: 4px;
    cursor: pointer;
    user-select: none;
}

.timeline:active {
    cursor: grabbing;
}

.timeline-progress {
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6);
    border-radius: 4px;
    pointer-events: none;
}

.timeline-handle {
    position: absolute;
    top: 50%;
    width: 16px;
    height: 16px;
    background: white;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    pointer-events: none;
}

.timeline-marker {
    position: absolute;
    top: 50%;
    width: 4px;
    height: 16px;
    background: #f59e0b;
    transform: translate(-50%, -50%);
    cursor: pointer;
    border-radius: 2px;
    transition: all 0.2s;
}

.timeline-marker:hover,
.timeline-marker.highlighted {
    background: #fbbf24;
    height: 20px;
    box-shadow: 0 0 8px rgba(245, 158, 11, 0.5);
}

.markers-labels {
    position: relative;
    height: 24px;
    margin-top: 5px;
}

.marker-label {
    position: absolute;
    transform: translateX(-50%);
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    color: var(--text-muted);
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
}

.marker-label:hover,
.marker-label.highlighted {
    background: var(--border);
    border-color: #f59e0b;
    color: var(--text-primary);
}

.marker-label.active {
    background: #f59e0b;
    border-color: #f59e0b;
    color: #000;
}

.playback-controls {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-top: 12px;
}

.volume-controls {
    display: flex;
    align-items: center;
    gap: 8px;
}

.mute-btn {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s;
}

.mute-btn:hover {
    color: var(--text-primary);
}

.volume-slider {
    width: 80px;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: var(--border-light);
    border-radius: 2px;
    cursor: pointer;
}

.volume-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 12px;
    height: 12px;
    background: var(--text-primary);
    border-radius: 50%;
    cursor: pointer;
    transition: transform 0.2s;
}

.volume-slider::-webkit-slider-thumb:hover {
    transform: scale(1.2);
}

.volume-slider::-moz-range-thumb {
    width: 12px;
    height: 12px;
    background: var(--text-primary);
    border-radius: 50%;
    cursor: pointer;
    border: none;
}

.speed-dropdown {
    position: relative;
}

.speed-btn {
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    color: var(--text-primary);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    align-items: center;
    gap: 8px;
}

.speed-btn:hover {
    background: var(--border);
    border-color: var(--border-hover);
}

.speed-btn svg {
    transition: transform 0.2s;
}

.speed-dropdown.open .speed-btn svg {
    transform: rotate(180deg);
}

.speed-options {
    position: absolute;
    bottom: 100%;
    right: 0;
    margin-bottom: 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    overflow: hidden;
    min-width: 80px;
}

.speed-option {
    width: 100%;
    background: none;
    border: none;
    color: var(--text-muted);
    padding: 10px 16px;
    text-align: left;
    cursor: pointer;
    font-size: 14px;
    transition: all 0.2s;
}

.speed-option:hover {
    background: var(--border);
    color: var(--text-primary);
}

.speed-option.active {
    background: #3b82f6;
    color: var(--text-primary);
}

.loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 50vh;
    color: var(--text-muted);
}

/* Buffering overlay */
.buffering-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--overlay);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 20;
    border-radius: 12px;
}

.buffering-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
}

.buffering-spinner {
    width: 48px;
    height: 48px;
    border: 3px solid var(--border-light);
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

.buffering-text {
    color: var(--text-muted);
    font-size: 14px;
}

.video-grid.videos-loading {
    opacity: 0.5;
}

.spotlight-view.videos-loading {
    /* Don't dim spotlight view as much, just show overlay */
}

/* Play button loading state */
.play-btn.loading {
    background: var(--border-light);
    cursor: wait;
}

.play-btn:disabled {
    opacity: 0.7;
    cursor: not-allowed;
}

.play-btn:disabled:hover {
    transform: none;
    box-shadow: none;
}

.loading-spinner {
    width: 20px;
    height: 20px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: var(--text-primary);
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

/* Center play button overlay for collection videos */
.video-center-play {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    z-index: 5;
}

.center-play-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 80px;
    height: 80px;
    background: rgba(180, 120, 20, 0.6);
    border-radius: 50%;
    color: rgba(255, 220, 150, 0.95);
    transition: all 0.3s;
    padding-left: 6px; /* Shift triangle right for visual centering */
}

.center-play-btn:hover {
    background: rgba(200, 140, 30, 0.75);
    transform: scale(1.1);
}

.video-center-play.playing .center-play-btn {
    opacity: 0;
    transform: scale(0.8);
}

.spotlight-video .center-play-btn {
    width: 100px;
    height: 100px;
    padding-left: 8px;
}

/* Collection Type Styles */
.collection-video {
    display: flex;
    flex-direction: column;
}

.collection-video video {
    flex: 1;
    min-height: 0;
}

.video-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: var(--bg-page);
    border-top: 1px solid var(--border);
}

.video-play-btn {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: linear-gradient(135deg, #f59e0b, #d97706);
    border: none;
    color: white;
    font-size: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    transition: transform 0.2s;
}

.video-play-btn:hover {
    transform: scale(1.05);
}

.play-icon-small {
    margin-left: 2px;
}

.pause-icon-small {
    letter-spacing: 1px;
    font-size: 10px;
}

.video-timeline {
    flex: 1;
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    cursor: pointer;
    position: relative;
    user-select: none;
}

.video-timeline:active {
    cursor: grabbing;
}

.video-timeline-progress {
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    background: linear-gradient(90deg, #f59e0b, #d97706);
    border-radius: 3px;
    pointer-events: none;
}

.video-time {
    font-size: 11px;
    color: var(--text-faint);
    font-variant-numeric: tabular-nums;
    min-width: 40px;
    text-align: right;
}

/* Collection controls container */
.collection-controls {
    border-top: 2px solid rgba(245, 158, 11, 0.3);
}

.play-btn.collection {
    background: linear-gradient(135deg, #f59e0b, #d97706);
}

.play-btn.collection:hover {
    box-shadow: 0 4px 20px rgba(245, 158, 11, 0.4);
}

.timeline.collection .timeline-progress {
    background: linear-gradient(90deg, #f59e0b, #d97706);
}

/* Collection spotlight styling */
.collection-spotlight .sidebar-video.active {
    border-color: #f59e0b;
}
</style>
