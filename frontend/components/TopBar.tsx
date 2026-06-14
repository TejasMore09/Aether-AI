'use client'

export default function TopBar() {
  return (
    <header className="fixed top-0 right-0 w-[calc(100%-16rem)] border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-md flex justify-between items-center h-16 px-8 z-40">
      <div className="font-mono text-xs uppercase text-zinc-500 flex items-center gap-2">
        <span className="material-symbols-outlined text-[16px]">search</span>
        <span>Command Center / Global Overview</span>
      </div>
      <div className="flex items-center gap-6">
        <button className="text-zinc-500 hover:text-white hover:bg-zinc-900 transition-colors focus:ring-1 focus:ring-white p-1 rounded-none">
          <span className="material-symbols-outlined">notifications</span>
        </button>
        <button className="text-zinc-500 hover:text-white hover:bg-zinc-900 transition-colors focus:ring-1 focus:ring-white p-1 rounded-none">
          <span className="material-symbols-outlined">settings</span>
        </button>
        <div className="w-8 h-8 bg-zinc-800 border border-zinc-700 overflow-hidden ml-2">
          <img alt="Executive User Profile" className="w-full h-full object-cover" src="https://lh3.googleusercontent.com/aida-public/AB6AXuBovzpRp0xPrQzuxKt7VB9oeiMH_WrccsTBWiIiG0eTc5ordDMxg0cRZqxp55PczDJhR07e2dkFtlEPQE4mnAjwquwEQuix5kAZN6lXWW-H2zADnH-_78YrtgDZAONuBvCthB-UI8x0yA_zvWpAtY-8nei_YoWC6U3ZZzfrjutEJVXR0tmjY3xA-MGA7ZdJwR6p0aFScNzfqmFPDi_nvHxRev58EgqEKkDBEDwl8e5c-6Z37-CUfv0vwL9yEaFQd3juhyMrepNs39Sp"/>
        </div>
      </div>
    </header>
  )
}
