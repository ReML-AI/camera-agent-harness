import { ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  accent?: string;
  children: ReactNode;
}

export function SlideShell({ title, subtitle, accent = 'border-blue-500', children }: Props) {
  return (
    <div className={`h-full flex flex-col bg-white border-l-4 ${accent} px-10 py-8 overflow-y-auto`}>
      <div className="mb-6 flex-shrink-0">
        <h2 className="text-2xl font-bold text-gray-900">{title}</h2>
        {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
      </div>
      <div className="flex-1 min-h-0">
        {children}
      </div>
    </div>
  );
}
