import { useState, useRef, useEffect } from 'react';
import { Settings, Presentation } from 'lucide-react';

type ToolView = 'debrief_report';

interface Props {
  onSelectView: (view: ToolView) => void;
}

const MENU_ITEMS: { view: ToolView; label: string; icon: typeof Settings; description: string }[] = [
  { view: 'debrief_report', label: 'Slide Report', icon: Presentation, description: 'View debrief slide report' },
];

export function ToolsMenu({ onSelectView }: Props) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-md transition-colors"
      >
        <Settings size={16} />
        Tools
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-50">
          {MENU_ITEMS.map((item) => (
            <button
              key={item.view}
              className="w-full text-left px-3 py-2 hover:bg-gray-50 transition-colors flex items-center gap-2.5"
              onClick={() => {
                onSelectView(item.view);
                setOpen(false);
              }}
            >
              <item.icon size={14} className="text-gray-400 flex-shrink-0" />
              <div>
                <p className="text-sm text-gray-700">{item.label}</p>
                <p className="text-xs text-gray-400">{item.description}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
