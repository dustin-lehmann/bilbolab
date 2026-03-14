# Dissertation Video Server

A web server for hosting and viewing synchronized experiment videos.

## Features

- Grid layout for multiple synchronized videos (adaptive: 2, 3, 4+ videos)
- Play/pause all videos simultaneously
- Timeline with markers for quick navigation
- Keyboard shortcuts (Space, Arrow keys)
- Playback speed control

## Setup

### Backend (Python)

```bash
cd software/extensions/diss_server
pip install -r requirements.txt
python server.py
```

The server runs on `http://localhost:5050`

### Frontend (Vite + Vue)

```bash
cd software/extensions/diss_server/frontend
npm install
npm run dev
```

The dev server runs on `http://localhost:9300`

## Usage

1. Put your video files in the `videos/` directory
2. Edit `experiments.json` to define your experiments
3. Start both servers
4. Open `http://localhost:9300` in your browser

## Configuration

Edit `experiments.json` to define experiments:

```json
{
  "experiments": [
    {
      "id": "exp_1",
      "title": "Experiment Name",
      "description": "Description of the experiment",
      "date": "2024-01-15",
      "videos": [
        {"name": "Front View", "file": "video1.mp4"},
        {"name": "Plot Animation", "file": "plot.mp4"}
      ],
      "markers": [
        {"time": 0, "label": "Start"},
        {"time": 10.5, "label": "Event 1"},
        {"time": 25.0, "label": "End"}
      ]
    }
  ]
}
```

## Keyboard Shortcuts

- `Space` - Play/Pause
- `Left Arrow` - Seek back 5 seconds
- `Right Arrow` - Seek forward 5 seconds

## Video Formats

Supported formats: `.mp4`, `.webm`, `.mov`, `.avi`

For best compatibility, use H.264 encoded MP4 files.
