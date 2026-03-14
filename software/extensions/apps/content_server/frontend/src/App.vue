<template>
    <div class="app-container" v-if="isAdminRoute">
        <router-view />
    </div>
    <div class="app-container" v-else>
        <header class="header">
            <div class="header-left">
                <button class="sidebar-toggle" data-tour="sidebar" @click="toggleSidebar" :title="sidebarOpen ? 'Close navigation' : 'Open navigation'">
                    <svg v-if="!sidebarOpen" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="3" y1="12" x2="21" y2="12"/>
                        <line x1="3" y1="6" x2="21" y2="6"/>
                        <line x1="3" y1="18" x2="21" y2="18"/>
                    </svg>
                    <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                </button>
                <router-link to="/" class="logo" data-tour="logo" @click="clearSearch">
                    <img v-if="settings.logo" :src="`/${settings.logo}`" alt="Logo" class="logo-img">
                    <span v-else class="logo-icon">&#9654;</span>
                    <span class="logo-text">{{ settings.title || 'Additional Material' }}</span>
                </router-link>
            </div>

            <div class="search-container">
                <div class="search-box" data-tour="search">
                    <svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="11" cy="11" r="8"/>
                        <path d="m21 21-4.35-4.35"/>
                    </svg>
                    <input
                        type="text"
                        v-model="searchQuery"
                        @input="onSearchInput"
                        @focus="showResults = true"
                        placeholder="Search material..."
                        class="search-input"
                    >
                    <button v-if="searchQuery" class="clear-btn" @click="clearSearch">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
                <button v-if="isAdmin && viewingItemId" class="help-btn edit-item-btn" @click="openInlineEdit" title="Edit this item">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                </button>
                <router-link v-if="hasAdminToken" to="/admin" class="help-btn" title="Admin Panel">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="3"/>
                        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                    </svg>
                </router-link>
                <button class="help-btn" data-tour="theme" @click="toggleTheme" :title="isDark ? 'Switch to light mode' : 'Switch to dark mode'">
                    <svg v-if="isDark" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                    </svg>
                    <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                    </svg>
                </button>
                <button class="help-btn" data-tour="help" @click="showHelpModal = true" title="Help">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                        <circle cx="12" cy="17" r="0.5" fill="currentColor"/>
                    </svg>
                </button>
                <button v-if="settings.tourEnabled" class="help-btn" @click="showTour = true" title="Take a tour">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/>
                        <line x1="4" y1="22" x2="4" y2="15"/>
                    </svg>
                </button>

                <div class="search-results" v-if="showResults && searchQuery && searchResults.length > 0">
                    <router-link
                        v-for="result in searchResults"
                        :key="result.id"
                        :to="getSearchResultRoute(result)"
                        class="search-result"
                        @click="clearSearch"
                    >
                        <div class="result-header">
                            <span v-if="result.type === 'folder'" class="result-type folder">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                                </svg>
                                Folder
                            </span>
                            <span v-else-if="result.experimentType === 'pdf'" class="result-type pdf">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                    <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" stroke-width="2"/>
                                </svg>
                                PDF
                            </span>
                            <span v-else-if="result.experimentType === 'figures'" class="result-type figures">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                                    <circle cx="8.5" cy="8.5" r="1.5"/>
                                    <polyline points="21 15 16 10 5 21"/>
                                </svg>
                                Figure Collection
                            </span>
                            <span v-else-if="result.experimentType === 'code'" class="result-type code">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="16 18 22 12 16 6"/>
                                    <polyline points="8 6 2 12 8 18"/>
                                </svg>
                                Code
                            </span>
                            <span v-else-if="result.experimentType === 'video'" class="result-type video">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polygon points="5 3 19 12 5 21 5 3"/>
                                </svg>
                                Video
                            </span>
                            <span v-else-if="result.experimentType === 'collection'" class="result-type collection">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                </svg>
                                Video Collection
                            </span>
                            <span v-else-if="result.experimentType === 'interactive'" class="result-type interactive">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                </svg>
                                Interactive Example
                            </span>
                            <span v-else-if="result.experimentType === 'model3d'" class="result-type model3d">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                    <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                                    <line x1="12" y1="22.08" x2="12" y2="12"/>
                                </svg>
                                3D Model
                            </span>
                            <span v-else class="result-type experiment">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"/>
                                    <path d="M12 6v6l4 2"/>
                                </svg>
                                Synchronized Videos
                            </span>
                        </div>
                        <div class="result-title">{{ result.title }}</div>
                        <div class="result-meta">
                            <span class="result-path" v-if="result.folderPath && result.folderPath.length > 0">
                                {{ result.folderPath.map(f => f.name).join(' / ') }}
                            </span>
                            <span v-if="result.type === 'folder'" class="result-count">{{ result.experimentCount }} {{ result.experimentCount === 1 ? 'element' : 'elements' }}</span>
                            <span v-else-if="result.experimentType === 'pdf'" class="result-count pdf">1 document</span>
                            <span v-else-if="result.experimentType === 'figures'" class="result-count figures">{{ result.videoCount || 0 }} {{ (result.videoCount || 0) === 1 ? 'figure' : 'figures' }}</span>
                            <span v-else-if="result.experimentType === 'code'" class="result-count code">{{ result.language || 'code' }}</span>
                            <span v-else-if="result.experimentType === 'interactive'" class="result-count interactive">Interactive</span>
                            <span v-else-if="result.experimentType === 'model3d'" class="result-count model3d">3D Model</span>
                            <span v-else class="result-count" :class="result.experimentType === 'collection' ? 'collection' : ''">{{ result.videoCount }} {{ result.experimentType === 'collection' ? (result.videoCount === 1 ? 'clip' : 'clips') : (result.videoCount === 1 ? 'video' : 'videos') }}</span>
                        </div>
                    </router-link>
                </div>

                <div class="search-results" v-if="showResults && searchQuery && searchResults.length === 0 && !isSearching">
                    <div class="no-results">No results found</div>
                </div>
            </div>
        </header>

        <div class="content-wrapper">
            <!-- Sidebar -->
            <aside class="sidebar" data-tour="sidebar-panel" :class="{ open: sidebarOpen }">
                <div class="sidebar-header">
                    <span class="sidebar-title">Navigation</span>
                    <button class="collapse-all-btn" @click="collapseAll" title="Collapse all">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="4 14 10 14 10 20"/>
                            <polyline points="20 10 14 10 14 4"/>
                            <line x1="14" y1="10" x2="21" y2="3"/>
                            <line x1="3" y1="21" x2="10" y2="14"/>
                        </svg>
                    </button>
                </div>
                <nav class="sidebar-nav">
                    <router-link to="/" class="nav-item home-link" @click="closeSidebarOnMobile">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                            <polyline points="9 22 9 12 15 12 15 22"/>
                        </svg>
                        <span>Home</span>
                    </router-link>

                    <div class="nav-tree">
                        <template v-for="folder in structure.folders" :key="folder.id">
                            <NavFolder
                                :folder="folder"
                                :expanded-folders="expandedFolders"
                                :depth="0"
                                @toggle="toggleFolder"
                                @navigate="closeSidebarOnMobile"
                            />
                        </template>
                    </div>
                </nav>
            </aside>

            <!-- Main content -->
            <main class="main-content" data-tour="content" :class="{ 'sidebar-open': sidebarOpen }" @click="showResults = false">
                <router-view :key="viewKey" :settings="settings" />
            </main>
        </div>

        <!-- Inline Edit Modal (admin) -->
        <Teleport to="body">
            <div v-if="inlineEdit.show" class="ie-overlay" @click.self="closeInlineEdit">
                <div class="ie-modal">
                    <div class="ie-header">
                        <h2>Edit Item</h2>
                        <div class="ie-header-actions">
                            <a class="ie-open-tab" :href="`/admin/edit/${inlineEdit.itemId}`" target="_blank" title="Open in full editor">
                                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                                    <polyline points="15 3 21 3 21 9"/>
                                    <line x1="10" y1="14" x2="21" y2="3"/>
                                </svg>
                            </a>
                            <button class="ie-close" @click="closeInlineEdit">&times;</button>
                        </div>
                    </div>
                    <div class="ie-body">
                        <ItemEditForm :form="inlineEdit.form" :available-files="inlineAvailableFiles"
                            show-thumbnail :generating-thumbnail="inlineEdit.generatingThumb"
                            @generate-thumbnail="generateThumbnail" @upload-thumbnail="uploadThumbnail">
                            <template #files>
                                <div class="ief-card">
                                    <h3>Files</h3>
                                    <!-- existing file chips and drop zone, but using ief-card class -->
                                    <div class="ie-chips">
                                        <span v-for="f in inlineEdit.files" :key="f" class="ie-chip">
                                            {{ f }}
                                            <button @click="inlineDeleteFile(f)">&times;</button>
                                        </span>
                                        <span v-for="(f, i) in inlineEdit.pending" :key="'p'+i" class="ie-chip ie-chip-pending">
                                            {{ f.name }}
                                            <button @click="inlineEdit.pending.splice(i, 1)">&times;</button>
                                        </span>
                                        <span v-if="inlineEdit.files.length === 0 && inlineEdit.pending.length === 0" class="ie-no-files">No files</span>
                                    </div>
                                    <div class="ie-drop" :class="{over: inlineEdit.dragover}"
                                         @dragover.prevent="inlineEdit.dragover=true"
                                         @dragleave="inlineEdit.dragover=false"
                                         @drop.prevent="inlineHandleDrop">
                                        <input type="file" multiple ref="inlineFileInput" @change="inlineHandleFileSelect" style="display:none">
                                        <span class="ie-drop-label">Drop files or <button class="ie-link" @click="$refs.inlineFileInput.click()">browse</button></span>
                                    </div>
                                </div>
                            </template>
                        </ItemEditForm>
                    </div>
                    <div class="ie-footer">
                        <button class="ie-btn ie-btn-ghost" @click="closeInlineEdit">Cancel</button>
                        <button class="ie-btn ie-btn-primary" @click="saveInlineEdit" :disabled="!inlineEdit.form.title.trim()">Save Changes</button>
                    </div>
                </div>
            </div>
        </Teleport>

        <!-- Tour -->
        <TourOverlay :active="showTour" :steps="tourSteps" @close="onTourClose" />

        <!-- Help Modal -->
        <div v-if="showHelpModal" class="modal-overlay" @click.self="showHelpModal = false">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>About This Application</h2>
                    <button class="modal-close" @click="showHelpModal = false">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M18 6L6 18M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
                <div class="modal-body">
                    <p class="help-intro">
                        This application provides access to additional materials organized in folders.
                        Browse through the navigation or use the search bar to find specific content.
                    </p>

                    <h3>Material Types</h3>
                    <div class="help-types">
                        <div class="help-type">
                            <span class="help-type-badge video">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polygon points="5 3 19 12 5 21 5 3"/>
                                </svg>
                                Video
                            </span>
                            <p>A single video with optional timeline markers and annotations.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge synchronized">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"/>
                                    <path d="M12 6v6l4 2"/>
                                </svg>
                                Synchronized Videos
                            </span>
                            <p>Multiple videos that play together in sync with shared markers and annotations.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge collection">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                                </svg>
                                Video Collection
                            </span>
                            <p>A collection of independent video clips for comparison or grouped viewing.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge figures">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                                    <circle cx="8.5" cy="8.5" r="1.5"/>
                                    <polyline points="21 15 16 10 5 21"/>
                                </svg>
                                Figure Collection
                            </span>
                            <p>An image gallery containing figures, diagrams, or other visual content.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge pdf">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                </svg>
                                PDF
                            </span>
                            <p>PDF documents such as papers, reports, or presentations.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge code">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polyline points="16 18 22 12 16 6"/>
                                    <polyline points="8 6 2 12 8 18"/>
                                </svg>
                                Code
                            </span>
                            <p>Source code snippets with syntax highlighting.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge interactive">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                </svg>
                                Interactive Example
                            </span>
                            <p>Interactive simulations and visualizations you can explore.</p>
                        </div>
                        <div class="help-type">
                            <span class="help-type-badge model3d">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                                    <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
                                    <line x1="12" y1="22.08" x2="12" y2="12"/>
                                </svg>
                                3D Model
                            </span>
                            <p>3D models you can rotate, zoom, and explore from any angle.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <ThesisPanel :visible="thesisPanelVisible" :page="thesisPanelPage" @close="thesisPanelVisible = false" />
</template>

<script setup>
import { ref, computed, onMounted, provide, h, defineComponent, watch, nextTick } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useTracking } from './composables/useTracking.js'
import { useTheme } from './composables/useTheme.js'
import { useAuth } from './composables/useAuth.js'
import { useApi } from './composables/useApi.js'
import TourOverlay from './components/TourOverlay.vue'
import ThesisPanel from './components/ThesisPanel.vue'
import ItemEditForm from './components/admin/ItemEditForm.vue'
import { itemFormFromData } from './components/admin/itemFormHelpers.js'

const route = useRoute()

// Track visitor page views (only on public pages, skips /admin)
useTracking()

const { isDark, toggle: toggleTheme } = useTheme()

const isAdminRoute = computed(() => route.path.startsWith('/admin'))
const viewKey = ref(0)

// --- Tour ---
const showTour = ref(false)

const TYPE_LABELS = {
    video: 'Video',
    synchronized: 'Synchronized Videos',
    collection: 'Video Collection',
    pdf: 'PDF Document',
    figures: 'Figure Gallery',
    code: 'Code Snippet',
    interactive: 'Interactive Example',
    model3d: '3D Model',
}

const TYPE_DESCRIPTIONS = {
    video: 'A single video with optional timeline markers and annotations.',
    synchronized: 'Multiple videos playing together in sync with shared timeline markers and annotations.',
    collection: 'A collection of video clips for comparison or grouped viewing.',
    pdf: 'A PDF document such as a paper, report, or presentation.',
    figures: 'An image gallery with figures, diagrams, or plots.',
    code: 'Source code with syntax highlighting.',
    interactive: 'An interactive simulation or visualization you can explore.',
    model3d: 'A 3D model you can rotate, zoom, and explore from any angle.',
}

// Emitted by ExperimentList to let the tour expand accordion folders
const tourExpandFolder = ref(null)
provide('tourExpandFolder', tourExpandFolder)

// Find one example item per content type across all folders
function findExamplePerType(folders, parentFolderId = null) {
    const found = {} // type -> { item, folderId }
    function walk(folderList) {
        for (const folder of folderList) {
            if (folder.experiments) {
                for (const exp of folder.experiments) {
                    const type = exp.type || 'synchronized'
                    if (!found[type]) {
                        found[type] = { item: exp, folderId: folder.id }
                    }
                }
            }
            if (folder.folders) walk(folder.folders)
        }
    }
    walk(folders)
    return found
}

const tourSteps = computed(() => {
    const steps = [
        {
            selector: '[data-tour="logo"]',
            title: 'Welcome',
            description: 'This site provides additional material organized in folders. Click the logo anytime to return to the home page.'
        },
        {
            selector: '[data-tour="sidebar-panel"]',
            title: 'Navigation',
            description: 'The sidebar lets you browse all folders and content items. Expand folders to see what\'s inside and click items to jump to them.',
            onEnter: () => { sidebarOpen.value = true },
        },
        {
            selector: '[data-tour="search"]',
            title: 'Search',
            description: 'Use the search bar to quickly find specific material by name, description, or type.'
        },
        {
            selector: '[data-tour="content"]',
            title: 'Content Area',
            description: 'The main area shows folder contents and material. Click on any item to view it.'
        },
    ]

    // Add one step per content type, using an example item
    const folders = structure.value?.folders || []
    const isAccordion = settings.value.folderStyle === 'accordion'
    const typeExamples = findExamplePerType(folders)
    const typeOrder = ['video', 'synchronized', 'collection', 'figures', 'pdf', 'code', 'interactive', 'model3d']

    for (const type of typeOrder) {
        const entry = typeExamples[type]
        const step = {
            selector: entry ? `[data-tour-item="${entry.item.id}"]` : null,
            badge: TYPE_LABELS[type],
            badgeClass: type,
            title: TYPE_LABELS[type],
            description: TYPE_DESCRIPTIONS[type],
            image: `/tour/${type}.svg`,
        }
        if (entry && isAccordion) {
            const folderId = entry.folderId
            step.onEnter = () => { tourExpandFolder.value = folderId }
        }
        steps.push(step)
    }

    // Theme toggle
    steps.push({
        selector: '[data-tour="theme"]',
        title: 'Light & Dark Mode',
        description: 'Switch between dark and light themes. Your preference is saved automatically.'
    })

    // Help button last
    steps.push({
        selector: '[data-tour="help"]',
        title: 'Help & Tour',
        description: 'Click the question mark for info about content types. Use the flag icon to replay this tour anytime.'
    })

    return steps
})

function onTourClose() {
    showTour.value = false
    localStorage.setItem('tour_seen', '1')
}
const hasAdminToken = computed(() => !!localStorage.getItem('admin_token'))

const { isAdmin } = useAuth()
const { adminGet, adminPut, adminPost, adminDelete: adminDel } = useApi()
const router = useRouter()

// Detect if we're on an item viewer route and extract the item ID
const viewingItemId = computed(() => {
    const path = route.path
    const match = path.match(/^\/(experiment|video|pdf|figures|code|interactive|model3d)\/(.+)$/)
    return match ? match[2] : null
})

// --- Inline edit modal ---
const inlineFileInput = ref(null)
const inlineEdit = ref({
    show: false,
    itemId: null,
    form: {},
    files: [],
    pending: [],
    dragover: false
})

const inlineAvailableFiles = computed(() => {
    const files = [...inlineEdit.value.files, ...inlineEdit.value.pending.map(f => f.name)]
    return [...new Set(files)]
})

async function openInlineEdit() {
    const id = viewingItemId.value
    if (!id) return
    try {
        const data = await adminGet(`/api/admin/items/${id}`)
        if (data && !data.error) {
            inlineEdit.value = {
                show: true,
                itemId: id,
                form: itemFormFromData(data),
                files: data.files || [],
                pending: [],
                dragover: false,
                generatingThumb: false
            }
        }
    } catch (e) {
        console.error('Failed to load item for editing:', e)
    }
}

function closeInlineEdit() {
    inlineEdit.value.show = false
}

async function saveInlineEdit() {
    const id = inlineEdit.value.itemId
    if (!id) return
    await adminPut(`/api/admin/items/${id}`, inlineEdit.value.form)
    // Upload pending files
    if (inlineEdit.value.pending.length) {
        const form = new FormData()
        for (const f of inlineEdit.value.pending) form.append('file', f)
        await adminPost(`/api/admin/items/${id}/files`, form)
    }
    closeInlineEdit()
    // Force reload current view
    viewKey.value++
}

async function inlineDeleteFile(filename) {
    const id = inlineEdit.value.itemId
    if (!id) return
    await adminDel(`/api/admin/items/${id}/files/${filename}`)
    inlineEdit.value.files = inlineEdit.value.files.filter(f => f !== filename)
}

function inlineHandleFileSelect(e) {
    if (e.target.files.length) {
        inlineEdit.value.pending.push(...e.target.files)
    }
    e.target.value = ''
}

function inlineHandleDrop(e) {
    inlineEdit.value.dragover = false
    if (e.dataTransfer.files.length) {
        inlineEdit.value.pending.push(...e.dataTransfer.files)
    }
}

async function generateThumbnail() {
    const id = inlineEdit.value.itemId
    if (!id) return
    inlineEdit.value.generatingThumb = true
    try {
        const res = await adminPost(`/api/admin/thumbnails/${id}/generate`, {})
        if (res?.thumbnail) {
            inlineEdit.value.form.thumbnail = res.thumbnail
        }
    } catch (e) {
        console.error('Failed to generate thumbnail:', e)
    }
    inlineEdit.value.generatingThumb = false
}

async function uploadThumbnail(file) {
    if (!file) return
    const id = inlineEdit.value.itemId
    if (!id) return
    const form = new FormData()
    form.append('file', file)
    try {
        const res = await adminPost(`/api/admin/thumbnails/${id}`, form)
        if (res?.thumbnail) {
            inlineEdit.value.form.thumbnail = res.thumbnail
        }
    } catch (e) {
        console.error('Failed to upload thumbnail:', e)
    }
}

// Auto-open inline edit when navigated with ?inlineEdit=1
watch(() => route.fullPath, async () => {
    if (route.query.inlineEdit && isAdmin.value && viewingItemId.value) {
        router.replace({ path: route.path, query: {} })
        await nextTick()
        openInlineEdit()
    }
}, { immediate: true })

// NavFolder component defined inline
const NavFolder = defineComponent({
    name: 'NavFolder',
    props: {
        folder: Object,
        expandedFolders: Object,
        depth: Number
    },
    emits: ['toggle', 'navigate'],
    setup(props, { emit }) {
        const getItemRoute = (item) => {
            const type = item.type || 'synchronized'
            if (type === 'video') return `/video/${item.id}`
            if (type === 'pdf') return `/pdf/${item.id}`
            if (type === 'figures') return `/figures/${item.id}`
            if (type === 'code') return `/code/${item.id}`
            if (type === 'interactive') return `/interactive/${item.id}`
            if (type === 'model3d') return `/model3d/${item.id}`
            return `/experiment/${item.id}`
        }

        const getTypeClass = (type) => type || 'synchronized'

        const getTypeIcon = (type) => {
            const icons = {
                video: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('polygon', { points: '5 3 19 12 5 21 5 3' })
                ]),
                synchronized: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('circle', { cx: 12, cy: 12, r: 10 }),
                    h('path', { d: 'M12 6v6l4 2' })
                ]),
                collection: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'currentColor' }, [
                    h('path', { d: 'M4 19.5A2.5 2.5 0 0 1 6.5 17H20' }),
                    h('path', { d: 'M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z' })
                ]),
                pdf: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'currentColor' }, [
                    h('path', { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' })
                ]),
                figures: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('rect', { x: 3, y: 3, width: 18, height: 18, rx: 2, ry: 2 }),
                    h('circle', { cx: 8.5, cy: 8.5, r: 1.5 }),
                    h('polyline', { points: '21 15 16 10 5 21' })
                ]),
                code: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('polyline', { points: '16 18 22 12 16 6' }),
                    h('polyline', { points: '8 6 2 12 8 18' })
                ]),
                interactive: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('path', { d: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z' })
                ]),
                model3d: h('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                    h('path', { d: 'M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z' }),
                    h('polyline', { points: '3.27 6.96 12 12.01 20.73 6.96' }),
                    h('line', { x1: 12, y1: 22.08, x2: 12, y2: 12 })
                ])
            }
            return icons[type] || icons.synchronized
        }

        return () => {
            const isExpanded = props.expandedFolders[props.folder.id]
            const hasChildren = (props.folder.folders?.length > 0) || (props.folder.experiments?.length > 0)
            const paddingLeft = `${12 + props.depth * 16}px`

            const children = []

            // Folder header
            children.push(
                h('div', { class: 'nav-folder-header', style: { paddingLeft } }, [
                    h('button', {
                        class: ['nav-folder-toggle', { expanded: isExpanded, 'no-children': !hasChildren }],
                        onClick: () => emit('toggle', props.folder.id)
                    }, [
                        hasChildren ? h('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2 }, [
                            h('polyline', { points: '9 18 15 12 9 6' })
                        ]) : null
                    ]),
                    h(RouterLink, {
                        to: `/folder/${props.folder.id}`,
                        class: 'nav-folder-link',
                        onClick: () => emit('navigate'),
                        onDblclick: (e) => {
                            e.preventDefault()
                            emit('toggle', props.folder.id)
                        }
                    }, () => [
                        h('svg', { class: 'nav-folder-icon', width: 16, height: 16, viewBox: '0 0 24 24', fill: 'currentColor' }, [
                            h('path', { d: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z' })
                        ]),
                        h('span', { class: 'nav-folder-name' }, props.folder.name)
                    ])
                ])
            )

            // Children (if expanded)
            if (isExpanded && hasChildren) {
                const childElements = []

                // Subfolders
                if (props.folder.folders) {
                    props.folder.folders.forEach(subfolder => {
                        childElements.push(
                            h(NavFolder, {
                                key: subfolder.id,
                                folder: subfolder,
                                expandedFolders: props.expandedFolders,
                                depth: props.depth + 1,
                                onToggle: (id) => emit('toggle', id),
                                onNavigate: () => emit('navigate')
                            })
                        )
                    })
                }

                // Experiments
                if (props.folder.experiments) {
                    props.folder.experiments.forEach(exp => {
                        const expPaddingLeft = `${12 + (props.depth + 1) * 16}px`
                        childElements.push(
                            h(RouterLink, {
                                key: exp.id,
                                to: getItemRoute(exp),
                                class: ['nav-item', 'nav-experiment', getTypeClass(exp.type)],
                                style: { paddingLeft: expPaddingLeft },
                                onClick: () => emit('navigate')
                            }, () => [
                                h('span', { class: ['nav-item-icon', getTypeClass(exp.type)] }, [getTypeIcon(exp.type)]),
                                h('span', { class: 'nav-item-name' }, exp.title)
                            ])
                        )
                    })
                }

                children.push(h('div', { class: 'nav-folder-children' }, childElements))
            }

            return h('div', { class: 'nav-folder' }, children)
        }
    }
})

const settings = ref({
    title: 'Additional Material',
    folderStyle: 'accordion',
    logo: 'bilbolab_logo.png'
})

const searchQuery = ref('')
const searchResults = ref([])
const showResults = ref(false)
const isSearching = ref(false)
const sidebarOpen = ref(false)
const structure = ref({ folders: [], experiments: [] })
const expandedFolders = ref({})
const showHelpModal = ref(false)
let searchTimeout = null

provide('settings', settings)

// Thesis slide-in panel
const thesisPanelVisible = ref(false)
const thesisPanelPage = ref(null)

function openThesisPanel(page) {
    thesisPanelPage.value = page
    thesisPanelVisible.value = true
}

provide('openThesisPanel', openThesisPanel)

function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
    // Save preference
    localStorage.setItem('sidebarOpen', sidebarOpen.value.toString())
}

function closeSidebarOnMobile() {
    if (window.innerWidth < 768) {
        sidebarOpen.value = false
    }
}

function toggleFolder(folderId) {
    expandedFolders.value[folderId] = !expandedFolders.value[folderId]
}

function collapseAll() {
    expandedFolders.value = {}
}

// Find path to an item (folder or experiment) by ID
function findPathToItem(folders, targetId, currentPath = []) {
    for (const folder of folders) {
        // Check if this folder matches
        if (folder.id === targetId) {
            return currentPath
        }

        // Check experiments in this folder
        if (folder.experiments) {
            for (const exp of folder.experiments) {
                if (exp.id === targetId) {
                    return [...currentPath, folder.id]
                }
            }
        }

        // Recursively check subfolders
        if (folder.folders) {
            const result = findPathToItem(folder.folders, targetId, [...currentPath, folder.id])
            if (result) {
                return result
            }
        }
    }
    return null
}

// Expand path to current route item in sidebar
function expandPathToRoute() {
    const path = route.path
    let targetId = null

    // Extract ID from route
    if (path.startsWith('/folder/')) {
        targetId = path.replace('/folder/', '')
    } else if (path.startsWith('/experiment/')) {
        targetId = path.replace('/experiment/', '')
    } else if (path.startsWith('/video/')) {
        targetId = path.replace('/video/', '')
    } else if (path.startsWith('/pdf/')) {
        targetId = path.replace('/pdf/', '')
    } else if (path.startsWith('/figures/')) {
        targetId = path.replace('/figures/', '')
    } else if (path.startsWith('/code/')) {
        targetId = path.replace('/code/', '')
    } else if (path.startsWith('/interactive/')) {
        targetId = path.replace('/interactive/', '')
    } else if (path.startsWith('/model3d/')) {
        targetId = path.replace('/model3d/', '')
    }

    if (targetId && structure.value.folders) {
        const pathToItem = findPathToItem(structure.value.folders, targetId)
        if (pathToItem) {
            // Expand all folders in the path
            pathToItem.forEach(folderId => {
                expandedFolders.value[folderId] = true
            })
        }
    }
}

// Watch for route changes to expand sidebar path
watch(() => route.path, () => {
    expandPathToRoute()
})

async function onSearchInput() {
    if (searchTimeout) clearTimeout(searchTimeout)

    if (!searchQuery.value.trim()) {
        searchResults.value = []
        return
    }

    isSearching.value = true
    searchTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(searchQuery.value)}`)
            const data = await response.json()
            searchResults.value = data.results || []
        } catch (error) {
            console.error('Search failed:', error)
            searchResults.value = []
        }
        isSearching.value = false
    }, 200)
}

function clearSearch() {
    searchQuery.value = ''
    searchResults.value = []
    showResults.value = false
}

function getSearchResultRoute(result) {
    if (result.type === 'folder') {
        return `/folder/${result.id}`
    }
    if (result.experimentType === 'video') {
        return `/video/${result.id}`
    }
    if (result.experimentType === 'pdf') {
        return `/pdf/${result.id}`
    }
    if (result.experimentType === 'figures') {
        return `/figures/${result.id}`
    }
    if (result.experimentType === 'code') {
        return `/code/${result.id}`
    }
    if (result.experimentType === 'interactive') {
        return `/interactive/${result.id}`
    }
    if (result.experimentType === 'model3d') {
        return `/model3d/${result.id}`
    }
    return `/experiment/${result.id}`
}

onMounted(async () => {
    // Load settings
    try {
        const response = await fetch('/api/settings')
        const data = await response.json()
        settings.value = { ...settings.value, ...data }
    } catch (error) {
        console.error('Failed to load settings:', error)
    }

    // Load structure for sidebar
    try {
        const response = await fetch('/api/experiments')
        structure.value = await response.json()

        // Expand path to current route after structure is loaded
        expandPathToRoute()
    } catch (error) {
        console.error('Failed to load structure:', error)
    }

    // Restore sidebar state
    const savedSidebarState = localStorage.getItem('sidebarOpen')
    if (savedSidebarState !== null) {
        sidebarOpen.value = savedSidebarState === 'true'
    }

    // Show tour for new visitors (if enabled and on home page)
    if (settings.value.tourEnabled && !localStorage.getItem('tour_seen') && route.path === '/') {
        // Delay to let the page render
        setTimeout(() => { showTour.value = true }, 600)
    }
})
</script>

<style>
.app-container {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.header {
    background: var(--code-bg);
    border-bottom: 1px solid var(--border);
    padding: 10px 24px;
    flex-shrink: 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 24px;
    z-index: 100;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
}

.sidebar-toggle {
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    color: var(--text-muted);
    width: 36px;
    height: 36px;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
}

.sidebar-toggle:hover {
    background: var(--border);
    color: var(--text-primary);
    border-color: var(--border-hover);
}

.logo {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 20px;
    font-weight: 600;
    color: var(--text-primary);
    text-decoration: none;
    flex-shrink: 0;
}

.logo-text {
    position: relative;
    top: 5px;
}

.logo-img {
    height: 36px;
    width: auto;
}

.logo-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #3b82f6, #8b5cf6);
    border-radius: 8px;
    font-size: 14px;
}

.search-container {
    position: relative;
    width: 100%;
    max-width: 450px;
    display: flex;
    align-items: center;
}

.search-box {
    display: flex;
    align-items: center;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    padding: 0 12px;
    transition: border-color 0.2s;
    flex: 1;
}

.search-box:focus-within {
    border-color: #3b82f6;
}

.search-icon {
    color: var(--text-faint);
    flex-shrink: 0;
}

.search-input {
    flex: 1;
    background: none;
    border: none;
    color: var(--text-primary);
    font-size: 14px;
    padding: 10px 12px;
    outline: none;
}

.search-input::placeholder {
    color: var(--text-faint);
}

.clear-btn {
    background: none;
    border: none;
    color: var(--text-faint);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.2s;
}

.clear-btn:hover {
    color: var(--text-primary);
}

.search-results {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    margin-top: 8px;
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 8px;
    max-height: 400px;
    overflow-y: auto;
    z-index: 100;
    box-shadow: 0 8px 32px var(--overlay-light);
}

.search-result {
    display: block;
    padding: 12px 16px;
    text-decoration: none;
    color: inherit;
    border-bottom: 1px solid var(--border);
    transition: background 0.2s;
}

.search-result:last-child {
    border-bottom: none;
}

.search-result:hover {
    background: var(--border);
}

.result-header {
    margin-bottom: 4px;
}

.result-type {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    padding: 2px 6px;
    border-radius: 4px;
}

.result-type.folder {
    background: rgba(107, 114, 128, 0.2);
    color: #9ca3af;
}

.result-type.video {
    background: rgba(139, 92, 246, 0.2);
    color: #a78bfa;
}

.result-type.experiment {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
}

.result-type.collection {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
}

.result-type.pdf {
    background: rgba(239, 68, 68, 0.2);
    color: #f87171;
}

.result-type.figures {
    background: rgba(16, 185, 129, 0.2);
    color: #34d399;
}

.result-type.code {
    background: rgba(6, 182, 212, 0.2);
    color: #22d3ee;
}

.result-type.interactive {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
}

.result-type.model3d {
    background: rgba(14, 165, 233, 0.2);
    color: #38bdf8;
}

.result-title {
    font-weight: 500;
    margin-bottom: 4px;
}

.result-meta {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: var(--text-muted);
}

.result-path {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    margin-right: 12px;
}

.result-count {
    flex-shrink: 0;
    color: #3b82f6;
}

.result-count.collection {
    color: #f59e0b;
}

.result-count.pdf {
    color: #f87171;
}

.result-count.figures {
    color: #34d399;
}

.result-count.code {
    color: #22d3ee;
}

.no-results {
    padding: 16px;
    text-align: center;
    color: var(--text-faint);
}

/* Content wrapper with sidebar */
.content-wrapper {
    flex: 1;
    display: flex;
    min-height: 0;
    overflow: hidden;
}

/* Sidebar */
.sidebar {
    width: 280px;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    position: absolute;
    left: 0;
    top: 61px;
    bottom: 0;
    z-index: 50;
}

.sidebar.open {
    transform: translateX(0);
}

/* On larger screens, push content when sidebar is open */
@media (min-width: 1024px) {
    .main-content.sidebar-open {
        margin-left: 280px;
    }
}

.sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
}

.sidebar-title {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-faint);
}

.collapse-all-btn {
    background: none;
    border: none;
    color: var(--text-faint);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: all 0.2s;
}

.collapse-all-btn:hover {
    background: var(--bg-elevated);
    color: var(--text-primary);
}

.sidebar-nav {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    color: var(--text-muted);
    text-decoration: none;
    font-size: 13px;
    transition: all 0.15s;
    border-left: 2px solid transparent;
}

.nav-item:hover {
    background: var(--bg-elevated);
    color: var(--text-primary);
}

.nav-item.router-link-active {
    background: var(--bg-elevated);
    color: var(--text-primary);
    border-left-color: #3b82f6;
}

.home-link {
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 12px;
}

/* Nav tree */
.nav-tree {
    padding-top: 4px;
}

.nav-folder {
    user-select: none;
}

.nav-folder-header {
    display: flex;
    align-items: center;
    gap: 4px;
}

.nav-folder-toggle {
    background: none;
    border: none;
    color: var(--text-faint);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 4px;
    transition: all 0.15s;
    flex-shrink: 0;
    width: 20px;
    height: 20px;
}

.nav-folder-toggle:hover {
    background: var(--border);
    color: var(--text-primary);
}

.nav-folder-toggle svg {
    transition: transform 0.2s;
}

.nav-folder-toggle.expanded svg {
    transform: rotate(90deg);
}

.nav-folder-toggle.no-children {
    visibility: hidden;
}

.nav-folder-link {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 13px;
    border-radius: 4px;
    transition: all 0.15s;
    flex: 1;
    min-width: 0;
}

.nav-folder-link:hover {
    background: var(--bg-elevated);
    color: var(--text-primary);
}

.nav-folder-link.router-link-active {
    background: var(--bg-elevated);
    color: var(--text-primary);
}

.nav-folder-icon {
    color: #6b7280;
    flex-shrink: 0;
}

.nav-folder-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.nav-folder-children {
    /* Children are indented via paddingLeft */
}

/* Nav experiment items */
.nav-experiment {
    padding: 5px 8px;
    margin-left: 24px;
    border-radius: 4px;
    border-left: none;
}

.nav-item-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.nav-item-icon.video { color: #a78bfa; }
.nav-item-icon.synchronized { color: #60a5fa; }
.nav-item-icon.collection { color: #fbbf24; }
.nav-item-icon.pdf { color: #f87171; }
.nav-item-icon.figures { color: #a78bfa; }
.nav-item-icon.code { color: #22d3ee; }
.nav-item-icon.interactive { color: #34d399; }
.nav-item-icon.model3d { color: #38bdf8; }

.nav-item-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* Main content */
.main-content {
    flex: 1;
    padding: 20px 32px;
    overflow: auto;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    min-height: 0;
    transition: margin-left 0.3s ease;
    background: linear-gradient(90deg, var(--bg-page) 0%, var(--bg-header) 50%, var(--bg-page) 100%);
}

.main-content > * {
    width: 100%;
}

/* Mobile overlay */
@media (max-width: 1023px) {
    .sidebar.open::before {
        content: '';
        position: fixed;
        inset: 0;
        background: var(--overlay-light);
        z-index: -1;
    }
}

/* Help button */
.edit-item-btn {
    background: rgba(59, 130, 246, 0.15) !important;
    border-color: rgba(59, 130, 246, 0.3) !important;
    color: #60a5fa !important;
}
.edit-item-btn:hover {
    background: rgba(59, 130, 246, 0.25) !important;
    border-color: rgba(59, 130, 246, 0.5) !important;
    color: #93bbfd !important;
}

/* Inline Edit Modal */
.ie-overlay {
    position: fixed; inset: 0; background: rgba(0,0,0,0.65);
    display: flex; align-items: center; justify-content: center;
    z-index: 10000; padding: 20px;
}
.ie-modal {
    background: var(--bg-elevated); border: 1px solid var(--border);
    border-radius: 12px; width: 100%; max-width: 640px; max-height: 90vh;
    display: flex; flex-direction: column;
    box-shadow: 0 20px 60px rgba(0,0,0,0.4);
}
.ie-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 18px 22px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.ie-header h2 { font-size: 17px; font-weight: 600; margin: 0; }
.ie-header-actions { display: flex; align-items: center; gap: 8px; }
.ie-open-tab {
    display: flex; align-items: center; justify-content: center;
    width: 30px; height: 30px; border-radius: 6px;
    color: var(--text-faint); text-decoration: none; transition: all 0.15s;
}
.ie-open-tab:hover { color: var(--text-primary); background: var(--border); }
.ie-close {
    background: none; border: none; color: var(--text-faint); font-size: 22px;
    cursor: pointer; line-height: 1; padding: 0 4px; border-radius: 4px;
}
.ie-close:hover { color: var(--text-primary); background: var(--border); }
.ie-body { padding: 20px 22px; overflow-y: auto; flex: 1; }
.ie-footer {
    display: flex; justify-content: flex-end; gap: 8px;
    padding: 14px 22px; border-top: 1px solid var(--border); flex-shrink: 0;
}
.ie-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.ie-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; background: var(--code-bg); border: 1px solid var(--border);
    border-radius: 6px; font-size: 12px; color: var(--text-secondary);
}
.ie-chip button { background: none; border: none; color: var(--text-faint); cursor: pointer; font-size: 14px; padding: 0; line-height: 1; }
.ie-chip button:hover { color: #f87171; }
.ie-chip-pending { border-style: dashed; color: var(--text-faint); }
.ie-no-files { font-size: 12px; color: var(--text-faint); }
.ie-drop {
    border: 1px dashed var(--border); border-radius: 8px;
    padding: 14px; text-align: center; transition: all 0.15s;
}
.ie-drop.over { border-color: #3b82f6; background: rgba(59,130,246,0.04); }
.ie-drop-label { font-size: 12px; color: var(--text-faint); }
.ie-link { background: none; border: none; color: #3b82f6; cursor: pointer; font-size: 12px; text-decoration: underline; }
.ie-btn {
    padding: 8px 18px; border: none; border-radius: 8px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s;
}
.ie-btn-primary { background: #3b82f6; color: white; }
.ie-btn-primary:hover:not(:disabled) { background: #2563eb; }
.ie-btn-primary:disabled { opacity: 0.45; cursor: default; }
.ie-btn-ghost { background: transparent; color: var(--text-muted); border: 1px solid var(--border); }
.ie-btn-ghost:hover { background: var(--bg-elevated); color: var(--text-secondary); }
.ie-btn-sm { padding: 5px 12px; font-size: 11px; background: var(--bg-elevated); color: var(--text-muted); border: 1px solid var(--border); border-radius: 6px; cursor: pointer; }
.ie-btn-sm:hover:not(:disabled) { color: var(--text-secondary); border-color: var(--border-hover); }
.ie-btn-sm:disabled { opacity: 0.45; cursor: default; }

.help-btn {
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    color: var(--text-muted);
    width: 38px;
    height: 38px;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
    flex-shrink: 0;
    margin-left: 8px;
}

.help-btn:hover {
    background: var(--border);
    color: var(--text-primary);
    border-color: var(--border-hover);
}

/* Help modal */
.modal-overlay {
    position: fixed;
    inset: 0;
    background: var(--overlay);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 200;
    padding: 20px;
}

.modal-content {
    background: var(--bg-elevated);
    border: 1px solid var(--border-light);
    border-radius: 16px;
    max-width: 600px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 20px 60px var(--overlay-light);
}

.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    border-bottom: 1px solid var(--border-light);
}

.modal-header h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
}

.modal-close {
    background: none;
    border: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    transition: all 0.2s;
}

.modal-close:hover {
    background: var(--border);
    color: var(--text-primary);
}

.modal-body {
    padding: 24px;
}

.help-intro {
    color: var(--text-secondary);
    line-height: 1.6;
    margin-bottom: 24px;
}

.modal-body h3 {
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 16px;
    color: var(--text-primary);
}

.help-types {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.help-type {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
}

.help-type p {
    margin: 8px 0 0;
    color: var(--text-muted);
    font-size: 14px;
    line-height: 1.5;
}

.help-type-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
}

.help-type-badge.video {
    background: rgba(139, 92, 246, 0.2);
    color: #a78bfa;
}

.help-type-badge.synchronized {
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
}

.help-type-badge.collection {
    background: rgba(245, 158, 11, 0.2);
    color: #fbbf24;
}

.help-type-badge.figures {
    background: rgba(168, 85, 247, 0.2);
    color: #c084fc;
}

.help-type-badge.pdf {
    background: rgba(239, 68, 68, 0.2);
    color: #f87171;
}

.help-type-badge.code {
    background: rgba(6, 182, 212, 0.2);
    color: #22d3ee;
}

.help-type-badge.interactive {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
}
.help-type-badge.model3d {
    background: rgba(14, 165, 233, 0.2);
    color: #38bdf8;
}
</style>
