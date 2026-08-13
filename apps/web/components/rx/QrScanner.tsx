"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Camera QR scanner using the browser's native BarcodeDetector.
 *
 * No bundled decoding library on purpose: this keeps the public dispense page tiny, which
 * matters when a pharmacist opens it on an old phone over a slow connection. Browsers
 * without BarcodeDetector fall back to the manual code + PIN path, which is always available.
 */
export function QrScanner({ onResult, onError }: { onResult: (value: string) => void; onError: (message: string) => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [status, setStatus] = useState("Starting camera...");

  useEffect(() => {
    let stream: MediaStream | null = null;
    let frame = 0;
    let stopped = false;

    async function start() {
      const DetectorClass = (window as unknown as { BarcodeDetector?: new (options: { formats: string[] }) => { detect: (source: CanvasImageSource) => Promise<{ rawValue: string }[]> } }).BarcodeDetector;
      if (!DetectorClass) {
        onError("This browser cannot scan QR codes. Enter the code and PIN below instead.");
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        onError("No camera available. Enter the code and PIN below instead.");
        return;
      }

      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      } catch {
        onError("Camera permission was refused. Enter the code and PIN below instead.");
        return;
      }
      if (stopped || !videoRef.current) return;

      videoRef.current.srcObject = stream;
      await videoRef.current.play().catch(() => undefined);
      setStatus("Point the camera at the QR code");

      const detector = new DetectorClass({ formats: ["qr_code"] });
      const tick = async () => {
        if (stopped || !videoRef.current) return;
        try {
          const codes = await detector.detect(videoRef.current);
          if (codes.length > 0 && codes[0].rawValue) {
            onResult(codes[0].rawValue);
            return;
          }
        } catch {
          // A dropped frame is normal while focusing; keep scanning.
        }
        frame = requestAnimationFrame(() => void tick());
      };
      frame = requestAnimationFrame(() => void tick());
    }

    void start();
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [onError, onResult]);

  return (
    <div className="qr-scanner">
      <video ref={videoRef} muted playsInline />
      <p className="muted small">{status}</p>
    </div>
  );
}
