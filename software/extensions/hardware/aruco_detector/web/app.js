(function () {
    'use strict';

    // --- Configuration ---
    var PROCESS_WIDTH = 640;
    var MAX_MARKER_ID = 99;  // DICT_4X4_100: only IDs 0-99
    var AXIS_LENGTH_FACTOR = 0.4;


    // --- DOM Elements ---
    var video = document.getElementById('video');
    var canvas = document.getElementById('canvas');
    var overlay = document.getElementById('overlay');
    var canvasCtx = canvas.getContext('2d');
    var overlayCtx = overlay.getContext('2d');
    var fpsEl = document.getElementById('fps');
    var markerCountEl = document.getElementById('marker-count');
    var btnStart = document.getElementById('btn-start');
    var btnCamera = document.getElementById('btn-camera');
    var btnAxes = document.getElementById('btn-axes');
    var btnIds = document.getElementById('btn-ids');
    var startScreen = document.getElementById('start-screen');
    var statusBar = document.getElementById('status-bar');
    var controls = document.getElementById('controls');

    // --- State ---
    var detector = null;
    var running = false;
    var showAxes = true;
    var showIds = true;
    var useFrontCamera = false;
    var stream = null;
    var animFrameId = null;

    // FPS calculation
    var frameCount = 0;
    var lastFpsTime = 0;
    var currentFps = 0;

    // Processing canvas (offscreen, fixed width for performance)
    var procCanvas = document.createElement('canvas');
    var procCtx = procCanvas.getContext('2d', { willReadFrequently: true });

    // --- Initialization ---
    function init() {
        detector = new AR.Detector({
            dictionaryName: 'ARUCO_4X4_1000',
            maxHammingDistance: 1
        });

        btnStart.addEventListener('click', startCamera);
        btnCamera.addEventListener('click', toggleCamera);
        btnAxes.addEventListener('click', function () {
            showAxes = !showAxes;
            btnAxes.classList.toggle('active', showAxes);
        });
        btnIds.addEventListener('click', function () {
            showIds = !showIds;
            btnIds.classList.toggle('active', showIds);
        });
        // Hide controls until started
        statusBar.classList.add('hidden');
        controls.classList.add('hidden');
    }

    // --- Camera ---
    function startCamera() {
        var constraints = {
            video: {
                facingMode: useFrontCamera ? 'user' : 'environment',
                width: { ideal: 1280 },
                height: { ideal: 720 }
            },
            audio: false
        };

        navigator.mediaDevices.getUserMedia(constraints)
            .then(function (s) {
                if (stream) {
                    stream.getTracks().forEach(function (t) { t.stop(); });
                }
                stream = s;
                video.srcObject = stream;
                video.play();

                video.onloadedmetadata = function () {
                    setupCanvases();
                    startScreen.classList.add('hidden');
                    statusBar.classList.remove('hidden');
                    controls.classList.remove('hidden');

                    if (!running) {
                        running = true;
                        lastFpsTime = performance.now();
                        frameCount = 0;
                        requestAnimationFrame(processFrame);
                    }
                };
            })
            .catch(function (err) {
                alert('Camera error: ' + err.message);
            });
    }

    function toggleCamera() {
        useFrontCamera = !useFrontCamera;
        if (stream) {
            running = false;
            if (animFrameId) {
                cancelAnimationFrame(animFrameId);
                animFrameId = null;
            }
            startCamera();
        }
    }

    function setupCanvases() {
        var vw = video.videoWidth;
        var vh = video.videoHeight;

        // Display canvases match container
        var cw = window.innerWidth;
        var ch = window.innerHeight;
        canvas.width = cw;
        canvas.height = ch;
        overlay.width = cw;
        overlay.height = ch;

        // Processing canvas at fixed width
        var scale = PROCESS_WIDTH / vw;
        procCanvas.width = PROCESS_WIDTH;
        procCanvas.height = Math.round(vh * scale);
    }

    // --- Main Detection Loop ---
    function processFrame() {
        if (!running) return;
        animFrameId = requestAnimationFrame(processFrame);

        var vw = video.videoWidth;
        var vh = video.videoHeight;
        if (!vw || !vh) return;

        var cw = canvas.width;
        var ch = canvas.height;
        var pw = procCanvas.width;
        var ph = procCanvas.height;

        // Draw video to display canvas (cover mode)
        var videoAspect = vw / vh;
        var canvasAspect = cw / ch;
        var drawW, drawH, drawX, drawY;

        if (videoAspect > canvasAspect) {
            drawH = ch;
            drawW = ch * videoAspect;
            drawX = (cw - drawW) / 2;
            drawY = 0;
        } else {
            drawW = cw;
            drawH = cw / videoAspect;
            drawX = 0;
            drawY = (ch - drawH) / 2;
        }

        canvasCtx.drawImage(video, drawX, drawY, drawW, drawH);

        // Draw to processing canvas at reduced resolution
        procCtx.drawImage(video, 0, 0, pw, ph);
        var imageData = procCtx.getImageData(0, 0, pw, ph);

        // Detect markers
        var allMarkers = detector.detect({
            width: pw,
            height: ph,
            data: imageData.data
        });

        // Filter to DICT_4X4_100 range (IDs 0-99)
        var markers = [];
        for (var i = 0; i < allMarkers.length; i++) {
            if (allMarkers[i].id <= MAX_MARKER_ID) {
                markers.push(allMarkers[i]);
            }
        }

        // Scale factor from processing coords to display coords
        var scaleX = drawW / pw;
        var scaleY = drawH / ph;
        var offsetX = drawX;
        var offsetY = drawY;

        // Draw overlays
        overlayCtx.clearRect(0, 0, cw, ch);
        for (var m = 0; m < markers.length; m++) {
            drawMarkerOverlay(markers[m], scaleX, scaleY, offsetX, offsetY);
        }

        // Update FPS
        frameCount++;
        var now = performance.now();
        if (now - lastFpsTime >= 1000) {
            currentFps = Math.round(frameCount * 1000 / (now - lastFpsTime));
            frameCount = 0;
            lastFpsTime = now;
            fpsEl.textContent = currentFps + ' FPS';
        }

        markerCountEl.textContent = markers.length + (markers.length === 1 ? ' marker' : ' markers');
    }

    // --- Overlay Drawing ---
    function drawMarkerOverlay(marker, scaleX, scaleY, offsetX, offsetY) {
        var corners = marker.corners;
        var ctx = overlayCtx;

        // Transform corners from processing coords to display coords
        var dc = [];
        for (var i = 0; i < 4; i++) {
            dc.push({
                x: corners[i].x * scaleX + offsetX,
                y: corners[i].y * scaleY + offsetY
            });
        }

        // Draw marker outline (green quadrilateral)
        ctx.beginPath();
        ctx.moveTo(dc[0].x, dc[0].y);
        ctx.lineTo(dc[1].x, dc[1].y);
        ctx.lineTo(dc[2].x, dc[2].y);
        ctx.lineTo(dc[3].x, dc[3].y);
        ctx.closePath();
        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 2.5;
        ctx.stroke();

        // Draw thick top edge (corner[0] -> corner[1]) to indicate "upright" orientation
        ctx.beginPath();
        ctx.moveTo(dc[0].x, dc[0].y);
        ctx.lineTo(dc[1].x, dc[1].y);
        ctx.strokeStyle = '#ff4444';
        ctx.lineWidth = 6;
        ctx.stroke();

        // Mark corner[0] with a small circle (origin)
        ctx.beginPath();
        ctx.arc(dc[0].x, dc[0].y, 5, 0, 2 * Math.PI);
        ctx.fillStyle = '#00ff00';
        ctx.fill();

        // Draw ID label
        if (showIds) {
            var cx = (dc[0].x + dc[1].x + dc[2].x + dc[3].x) / 4;
            var cy = (dc[0].y + dc[1].y + dc[2].y + dc[3].y) / 4;

            // Compute marker size for font scaling
            var edgeLen = Math.sqrt(
                (dc[1].x - dc[0].x) * (dc[1].x - dc[0].x) +
                (dc[1].y - dc[0].y) * (dc[1].y - dc[0].y)
            );
            var fontSize = Math.max(14, Math.min(32, edgeLen * 0.3));

            ctx.font = 'bold ' + fontSize + 'px sans-serif';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';

            // Background for readability
            var text = 'ID ' + marker.id;
            var metrics = ctx.measureText(text);
            var textW = metrics.width + 8;
            var textH = fontSize + 4;
            ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
            ctx.fillRect(cx - textW / 2, cy - textH / 2, textW, textH);

            ctx.fillStyle = '#ffff00';
            ctx.fillText(text, cx, cy);
        }

        // Draw coordinate axes
        if (showAxes) {
            // X axis: corner[0] -> corner[1] (red)
            var axX = {
                x: dc[0].x + (dc[1].x - dc[0].x) * AXIS_LENGTH_FACTOR,
                y: dc[0].y + (dc[1].y - dc[0].y) * AXIS_LENGTH_FACTOR
            };
            // Y axis: corner[0] -> corner[3] (green)
            var axY = {
                x: dc[0].x + (dc[3].x - dc[0].x) * AXIS_LENGTH_FACTOR,
                y: dc[0].y + (dc[3].y - dc[0].y) * AXIS_LENGTH_FACTOR
            };
            // Z axis: toward center (blue, 2D approximation)
            var centerX = (dc[0].x + dc[2].x) / 2;
            var centerY = (dc[0].y + dc[2].y) / 2;
            var axZ = {
                x: dc[0].x + (centerX - dc[0].x) * AXIS_LENGTH_FACTOR * 0.7,
                y: dc[0].y + (centerY - dc[0].y) * AXIS_LENGTH_FACTOR * 0.7
            };

            drawArrow(ctx, dc[0].x, dc[0].y, axX.x, axX.y, '#ff0000', 2.5);
            drawArrow(ctx, dc[0].x, dc[0].y, axY.x, axY.y, '#00cc00', 2.5);
            drawArrow(ctx, dc[0].x, dc[0].y, axZ.x, axZ.y, '#4488ff', 2.5);
        }
    }

    function drawArrow(ctx, x1, y1, x2, y2, color, lineWidth) {
        var headLen = 8;
        var angle = Math.atan2(y2 - y1, x2 - x1);

        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.strokeStyle = color;
        ctx.lineWidth = lineWidth;
        ctx.stroke();

        // Arrowhead
        ctx.beginPath();
        ctx.moveTo(x2, y2);
        ctx.lineTo(
            x2 - headLen * Math.cos(angle - Math.PI / 6),
            y2 - headLen * Math.sin(angle - Math.PI / 6)
        );
        ctx.lineTo(
            x2 - headLen * Math.cos(angle + Math.PI / 6),
            y2 - headLen * Math.sin(angle + Math.PI / 6)
        );
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.fill();
    }

    // --- Handle resize ---
    window.addEventListener('resize', function () {
        if (running) {
            setupCanvases();
        }
    });

    // --- Start ---
    init();
})();
