let audioContext: AudioContext | null = null;

/**
 * Plays a simple, non-intrusive UI sound effect.
 * @param type - The type of sound to play ('confirm', 'alert', 'click').
 */
export function playSound(type: 'confirm' | 'alert' | 'click' = 'click') {
	try {
		if (!audioContext) {
			audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
		}
		const oscillator = audioContext.createOscillator();
		const gainNode = audioContext.createGain();

		oscillator.connect(gainNode);
		gainNode.connect(audioContext.destination);

		gainNode.gain.setValueAtTime(0.001, audioContext.currentTime);

		switch (type) {
			case 'confirm':
				oscillator.type = 'sine';
				oscillator.frequency.setValueAtTime(880, audioContext.currentTime);
				gainNode.gain.exponentialRampToValueAtTime(0.2, audioContext.currentTime + 0.01);
				gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.18);
				break;
			case 'alert':
				oscillator.type = 'square';
				oscillator.frequency.setValueAtTime(440, audioContext.currentTime);
				gainNode.gain.exponentialRampToValueAtTime(0.15, audioContext.currentTime + 0.01);
				gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.1);
				break;
			default: // 'click'
				oscillator.type = 'triangle';
				oscillator.frequency.setValueAtTime(660, audioContext.currentTime);
				gainNode.gain.exponentialRampToValueAtTime(0.1, audioContext.currentTime + 0.01);
				gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.08);
				break;
		}

		oscillator.start(audioContext.currentTime);
		oscillator.stop(audioContext.currentTime + 0.2);
	} catch (error) {
		// Silently fail if AudioContext is not supported or fails.
		console.error('Audio playback failed:', error);
	}
}