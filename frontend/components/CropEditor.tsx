"use client";

import { useCallback, useRef, useState } from "react";
import { Rnd } from "react-rnd";

type CropBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type CropEditorProps = {
  videoUrl: string;
  onCropReady: (crop: CropBox) => void;
};

export default function CropEditor({ videoUrl, onCropReady }: CropEditorProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  const [cropBox, setCropBox] = useState({
    x: 100,
    y: 50,
    width: 300,
    height: 500,
  });

  const calculateRealCrop = useCallback(
    (box: CropBox = cropBox) => {
      const video = videoRef.current;
      const wrapper = wrapperRef.current;

      if (!video || !wrapper) return;
      if (!video.videoWidth || !video.videoHeight) return;

      const displayedWidth = wrapper.clientWidth;
      const displayedHeight = wrapper.clientHeight;

      if (!displayedWidth || !displayedHeight) return;

      const scaleX = video.videoWidth / displayedWidth;
      const scaleY = video.videoHeight / displayedHeight;
      const x = Math.max(0, Math.min(box.x, displayedWidth));
      const y = Math.max(0, Math.min(box.y, displayedHeight));
      const width = Math.min(box.width, displayedWidth - x);
      const height = Math.min(box.height, displayedHeight - y);

      const realCrop = {
        x: Math.round(x * scaleX),
        y: Math.round(y * scaleY),
        width: Math.round(width * scaleX),
        height: Math.round(height * scaleY),
      };

      onCropReady(realCrop);
    },
    [cropBox, onCropReady]
  );

  function initializeCropBox() {
    const wrapper = wrapperRef.current;

    if (!wrapper) return;

    window.requestAnimationFrame(() => {
      const width = Math.max(120, Math.round(wrapper.clientWidth * 0.5));
      const height = Math.max(120, Math.round(wrapper.clientHeight * 0.5));
      const nextCropBox = {
        x: Math.max(0, Math.round((wrapper.clientWidth - width) / 2)),
        y: Math.max(0, Math.round((wrapper.clientHeight - height) / 2)),
        width,
        height,
      };

      setCropBox(nextCropBox);
      calculateRealCrop(nextCropBox);
    });
  }

  return (
    <div className="space-y-4">
      <div
        ref={wrapperRef}
        className="relative mx-auto w-full max-w-4xl overflow-hidden bg-black"
      >
        <video
          ref={videoRef}
          src={videoUrl}
          controls
          onLoadedMetadata={initializeCropBox}
          className="h-auto w-full"
        />

        <Rnd
          bounds="parent"
          size={{ width: cropBox.width, height: cropBox.height }}
          position={{ x: cropBox.x, y: cropBox.y }}
          onDragStop={(_, data) => {
            const nextCropBox = {
              ...cropBox,
              x: data.x,
              y: data.y,
            };

            setCropBox(nextCropBox);
            calculateRealCrop(nextCropBox);
          }}
          onResizeStop={(_, __, ref, ___, position) => {
            const nextCropBox = {
              x: position.x,
              y: position.y,
              width: ref.offsetWidth,
              height: ref.offsetHeight,
            };

            setCropBox(nextCropBox);
            calculateRealCrop(nextCropBox);
          }}
          className="border-4 border-white/90 bg-white/10"
        />
      </div>

      <button
        onClick={() => calculateRealCrop()}
        className="rounded bg-black px-4 py-2 text-white"
      >
        Use this crop
      </button>
    </div>
  );
}
