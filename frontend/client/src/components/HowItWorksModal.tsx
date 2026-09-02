/**
 * DRISHYAM visual reminder: a centered charcoal terminal player for a user-supplied platform walkthrough.
 * It never fetches external media and shows a truthful awaiting-video state until a local asset is supplied.
 */
import { useEffect, useRef, useState } from "react";
import { Expand, FolderOpen, Pause, Play, RotateCcw, Volume2, VolumeX, X } from "lucide-react";

type HowItWorksModalProps = {
  open: boolean;
  onClose: () => void;
  videoSrc?: string | null;
};

const rates = [0.5, 0.75, 1, 1.25, 1.5, 2];

function formatTime(value: number) {
  if (!Number.isFinite(value) || value < 0) return "00:00";
  const minutes = Math.floor(value / 60).toString().padStart(2, "0");
  const seconds = Math.floor(value % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export default function HowItWorksModal({ open, onClose, videoSrc }: HowItWorksModalProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRate] = useState(1);
  const [videoError, setVideoError] = useState(false);
  const hasSource = Boolean(videoSrc?.trim());

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (document.fullscreenElement) {
        void document.exitFullscreen();
        return;
      }
      onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);

  useEffect(() => {
    setPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    setVideoError(false);
  }, [videoSrc]);

  if (!open) return null;

  const togglePlay = async () => {
    const player = videoRef.current;
    if (!player || !hasSource) return;
    if (player.paused) {
      try {
        await player.play();
      } catch {
        setPlaying(false);
      }
    } else {
      player.pause();
    }
  };

  const seekTo = (value: number) => {
    const player = videoRef.current;
    if (!player) return;
    player.currentTime = value;
    setCurrentTime(value);
  };

  const changeRate = (nextRate: number) => {
    const player = videoRef.current;
    if (player) player.playbackRate = nextRate;
    setRate(nextRate);
  };

  const toggleMute = () => {
    const player = videoRef.current;
    if (!player) return;
    player.muted = !player.muted;
    setMuted(player.muted);
  };

  const toggleFullscreen = async () => {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      return;
    }
    await panelRef.current?.requestFullscreen?.();
  };

  return (
    <div className="fixed inset-0 z-[90] grid place-items-center bg-[#101312]/80 px-4 py-6 backdrop-blur-md" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="how-it-works-title" className="relative flex max-h-full w-full max-w-5xl flex-col overflow-hidden rounded-[22px] border border-white/15 bg-[#111513] text-[#edf0ea] shadow-[0_30px_100px_rgba(0,0,0,.55)]">
        <div className="flex items-center justify-between border-b border-white/10 bg-[#1a1f1c] px-4 py-3 sm:px-5">
          <div className="flex items-center gap-2" aria-label="Window controls"><button type="button" onClick={onClose} aria-label="Close walkthrough" className="grid h-3.5 w-3.5 place-items-center rounded-full bg-[#ff5f57] text-[0] transition hover:brightness-110"><X size={10} className="text-[#68221e]" /></button><span className="h-3.5 w-3.5 rounded-full bg-[#febc2e]"/><span className="h-3.5 w-3.5 rounded-full bg-[#28c840]"/></div>
          <div className="flex min-w-0 items-center gap-2 text-center"><FolderOpen size={16} className="shrink-0 text-[#6fb0eb]"/><p id="how-it-works-title" className="truncate font-mono text-[11px] font-bold tracking-[.05em] text-[#e6e9e2] sm:text-xs">drishyam — how-it-works.mp4</p></div>
          <button type="button" onClick={onClose} className="rounded-md px-2 py-1 font-mono text-[10px] text-[#aaaFA8] transition hover:bg-white/10 hover:text-white">ESC&nbsp; CLOSE</button>
        </div>

        <div className="flex items-center justify-between border-b border-[#27312b] bg-[#141a16] px-5 py-2 font-mono text-[9px] uppercase tracking-[.12em] text-[#95a39a]"><span><span className="text-[#47d868]">drishyam@home</span>:~/walkthrough $ ./play</span><span className="text-[#d7ae79]">* Made with AI</span></div>

        <div className="relative min-h-[300px] bg-[#080a09] sm:min-h-[440px]">
          {hasSource && !videoError ? <video ref={videoRef} className="absolute inset-0 h-full w-full object-contain" src={videoSrc ?? undefined} onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)} onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onError={() => setVideoError(true)} playsInline /> : <div className="absolute inset-0 grid place-items-center p-8 text-center"><div className="max-w-md"><div className="mx-auto grid h-16 w-16 place-items-center rounded-xl border border-[#2d4034] bg-[#132018] text-[#54d778]"><FolderOpen size={28}/></div><p className="mt-5 font-mono text-xs font-bold uppercase tracking-[.16em] text-[#54d778]">Walkthrough video awaiting upload</p><p className="mt-3 text-sm leading-6 text-[#aab2aa]">Your supplied local video will play here. The player controls are ready and no external media has been embedded.</p></div></div>}
          {hasSource && !videoError && <button type="button" onClick={togglePlay} aria-label={playing ? "Pause walkthrough" : "Play walkthrough"} className="absolute left-1/2 top-1/2 grid h-16 w-16 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-white/30 bg-black/45 text-white backdrop-blur transition hover:scale-105">{playing ? <Pause size={24} fill="currentColor"/> : <Play size={24} fill="currentColor" className="translate-x-0.5"/>}</button>}
        </div>

        <div className="border-t border-white/10 bg-[#111513] px-4 py-4 sm:px-5">
          <input aria-label="Video progress" type="range" min="0" max={Math.max(duration, 1)} step="0.1" value={Math.min(currentTime, Math.max(duration, 1))} disabled={!hasSource || videoError} onChange={(event) => seekTo(Number(event.target.value))} className="h-1 w-full cursor-pointer accent-[#9a2722] disabled:cursor-not-allowed disabled:opacity-30" />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2"><button type="button" onClick={togglePlay} disabled={!hasSource || videoError} className="grid h-9 w-9 place-items-center rounded-md border border-white/15 text-white transition hover:bg-white/10 disabled:opacity-30">{playing ? <Pause size={16} fill="currentColor"/> : <Play size={16} fill="currentColor"/>}</button><button type="button" onClick={() => seekTo(0)} disabled={!hasSource || videoError} aria-label="Restart video" className="grid h-9 w-9 place-items-center rounded-md border border-white/15 text-[#d9ded6] transition hover:bg-white/10 disabled:opacity-30"><RotateCcw size={15}/></button><button type="button" onClick={toggleMute} disabled={!hasSource || videoError} aria-label={muted ? "Unmute video" : "Mute video"} className="grid h-9 w-9 place-items-center rounded-md border border-white/15 text-[#d9ded6] transition hover:bg-white/10 disabled:opacity-30">{muted ? <VolumeX size={16}/> : <Volume2 size={16}/>}</button><span className="ml-1 font-mono text-[10px] text-[#bac3b8]">{formatTime(currentTime)} / {formatTime(duration)}</span></div><div className="flex items-center gap-2"><label className="sr-only" htmlFor="walkthrough-speed">Playback speed</label><select id="walkthrough-speed" value={rate} onChange={(event) => changeRate(Number(event.target.value))} disabled={!hasSource || videoError} className="h-9 rounded-md border border-white/15 bg-[#181e1a] px-2 font-mono text-[10px] text-[#dfe5dc] outline-none focus:border-[#54d778] disabled:opacity-30">{rates.map((value) => <option key={value} value={value}>{value}×</option>)}</select><button type="button" onClick={() => void toggleFullscreen()} aria-label="Toggle fullscreen player" className="grid h-9 w-9 place-items-center rounded-md border border-white/15 text-[#d9ded6] transition hover:bg-white/10"><Expand size={16}/></button></div></div>
        </div>
      </div>
    </div>
  );
}
