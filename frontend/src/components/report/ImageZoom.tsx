import { useState, useEffect, useCallback } from 'react';

interface Props {
  src: string;
  alt?: string;
  children: React.ReactNode;
  className?: string;
}

export function ImageZoom({ src, alt = '', children, className }: Props) {
  const [open, setOpen] = useState(false);
  const [visible, setVisible] = useState(false);

  const openLightbox = useCallback(() => {
    setOpen(true);
    // Double rAF ensures the element is mounted before we trigger the transition
    requestAnimationFrame(() => requestAnimationFrame(() => setVisible(true)));
  }, []);

  const closeLightbox = useCallback(() => {
    setVisible(false);
    setTimeout(() => setOpen(false), 350);
  }, []);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') closeLightbox(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, closeLightbox]);

  return (
    <>
      {/* Trigger wrapper */}
      <div
        className={`cursor-zoom-in group relative ${className ?? ''}`}
        onClick={openLightbox}
      >
        {children}
        {/* Hover hint */}
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none rounded-[inherit] overflow-hidden">
          <div className="bg-black/40 backdrop-blur-[2px] rounded-full px-3 py-1.5 flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 115 11a6 6 0 0112 0zm-2.5 0h-7m3.5-3.5v7" />
            </svg>
            <span className="text-white text-[11px] font-medium">Zoom</span>
          </div>
        </div>
      </div>

      {/* Lightbox overlay */}
      {open && (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center"
          onClick={closeLightbox}
          style={{
            backgroundColor: visible ? 'rgba(5, 5, 10, 0.88)' : 'rgba(5, 5, 10, 0)',
            backdropFilter: visible ? 'blur(6px)' : 'blur(0px)',
            transition: 'background-color 320ms ease, backdrop-filter 320ms ease',
          }}
        >
          {/* Image */}
          <img
            src={src}
            alt={alt}
            onClick={e => e.stopPropagation()}
            style={{
              maxWidth: '88vw',
              maxHeight: '88vh',
              objectFit: 'contain',
              borderRadius: '10px',
              boxShadow: '0 32px 96px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.08)',
              transform: visible ? 'scale(1) translateY(0)' : 'scale(0.18) translateY(40px)',
              opacity: visible ? 1 : 0,
              transition: visible
                ? 'transform 380ms cubic-bezier(0.34, 1.45, 0.64, 1), opacity 220ms ease'
                : 'transform 300ms cubic-bezier(0.4, 0, 1, 1), opacity 250ms ease',
            }}
          />

          {/* Close hint */}
          <div
            style={{
              position: 'fixed',
              bottom: '28px',
              left: '50%',
              transform: 'translateX(-50%)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              color: 'rgba(255,255,255,0.38)',
              fontSize: '12px',
              fontFamily: 'monospace',
              letterSpacing: '0.04em',
              opacity: visible ? 1 : 0,
              transition: 'opacity 320ms ease 120ms',
              pointerEvents: 'none',
            }}
          >
            <span style={{
              border: '1px solid rgba(255,255,255,0.2)',
              borderRadius: '4px',
              padding: '1px 6px',
              fontSize: '11px',
            }}>ESC</span>
            <span>or click to close</span>
          </div>
        </div>
      )}
    </>
  );
}
