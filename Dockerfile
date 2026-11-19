FROM python:3.11-slim

# Dependencias del sistema para OpenCV y Flet web
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements primero (cache de capas)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de la app
COPY . .

ENV OPENCV_FFMPEG_CAPTURE_OPTIONS="protocol_whitelist;file,rtp,udp,tcp|fflags;nobuffer|flags;low_delay|strict;-2|stimeout;3000000"

EXPOSE 8550
# Puerto MAVLink ArduPilot (UDP)
EXPOSE 14560/udp
# Puerto stream de vídeo RTP/UDP
EXPOSE 5004/udp

CMD ["flet", "run", "App_flet.py", "--web", "--port", "8550"]