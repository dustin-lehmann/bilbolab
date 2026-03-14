export const DEFAULT_OVERLAY_STYLE = {
    verticalPosition: 'bottom',
    horizontalPosition: 'center',
    fontSize: 16,
    fontColor: '#ffffff',
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    opacity: 0.8
}

export function defaultItemForm() {
    return {
        title: '', description: '', type: 'video',
        date: new Date().toISOString().split('T')[0],
        draft: false, thumbnail: '',
        videos: [], markers: [], figures: [],
        file: '', language: 'python', model: '',
        chapter: '', section: '', subsection: '', page: '',
        additionalInfo: '',
        overlays: [], overlayStyle: {}
    }
}

export function itemFormFromData(data) {
    return {
        title: data.title || '', description: data.description || '',
        type: data.type || 'synchronized', date: data.date || '',
        draft: data.draft || false, thumbnail: data.thumbnail || '',
        videos: (data.videos || []).map(v => ({
            ...v,
            overlays: v.overlays ? [...v.overlays] : [],
            overlayStyle: v.overlayStyle ? { ...v.overlayStyle } : {}
        })),
        markers: [...(data.markers || [])],
        figures: [...(data.figures || [])],
        file: data.file || '', language: data.language || 'python', model: data.model || '',
        chapter: data.chapter || '', section: data.section || '',
        subsection: data.subsection || '', page: data.page || '',
        additionalInfo: data.additionalInfo || '',
        overlays: data.overlays ? [...data.overlays] : [],
        overlayStyle: data.overlayStyle ? { ...data.overlayStyle } : {}
    }
}
