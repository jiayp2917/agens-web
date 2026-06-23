import { useRef, useState } from "react";
import { Volume2, VolumeX } from "lucide-react";

export function BgmToggle() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [blocked, setBlocked] = useState(false);

  const toggle = async () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (enabled) {
      audio.pause();
      setEnabled(false);
      return;
    }
    try {
      audio.volume = 0.42;
      await audio.play();
      setBlocked(false);
      setEnabled(true);
    } catch {
      setBlocked(true);
      setEnabled(false);
    }
  };

  return (
    <>
      <button
        className={`icon-btn bgm-btn ${enabled ? "is-on" : ""}`}
        onClick={toggle}
        aria-label={enabled ? "关闭背景音乐" : "播放背景音乐"}
        title={blocked ? "浏览器阻止自动播放，请再点一次" : enabled ? "关闭背景音乐" : "播放背景音乐"}
      >
        {enabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
      </button>
      <audio
        ref={audioRef}
        src="/assets/audio/bgm.flac"
        preload="none"
        loop
        onPlay={() => setEnabled(true)}
        onPause={() => setEnabled(false)}
      />
    </>
  );
}