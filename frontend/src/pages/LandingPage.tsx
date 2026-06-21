import { Link } from "react-router-dom";

import { Wordmark } from "@/components/ui/Wordmark";

const coverUrls = {
  anna: "https://covers.openlibrary.org/b/isbn/9780143035008-L.jpg",
  ivan: "https://covers.openlibrary.org/b/isbn/9780553210354-L.jpg",
  gatsby: "https://covers.openlibrary.org/b/isbn/9780743273565-L.jpg",
  nightingale: "https://covers.openlibrary.org/b/isbn/9780312577223-L.jpg",
  bookThief: "https://covers.openlibrary.org/b/isbn/9780375842207-L.jpg",
  pachinko: "https://covers.openlibrary.org/b/isbn/9781455563937-L.jpg",
  allLight: "https://covers.openlibrary.org/b/isbn/9781476746586-L.jpg"
};

const features = [
  {
    title: "Transparent picks",
    body: "See why each book is recommended."
  },
  {
    title: "TBR-first",
    body: "Choose from the books you already meant to read."
  },
  {
    title: "No AI summaries",
    body: "No fake summaries, no black-box book slop."
  }
];

const steps = [
  "Import or add books.",
  "Rate and track what you read.",
  "ShelfTxt reads your shelf signals.",
  "Pick one book with a clear reason."
];

function Cover({ src, title }: { src: string; title: string }) {
  return (
    <img
      src={src}
      alt={`${title} cover`}
      className="aspect-[2/3] w-full rounded-md border border-border object-cover shadow-2xl shadow-black/30"
      loading="lazy"
    />
  );
}

function DashboardVisual() {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-card sm:p-5">
      <div className="mb-4 flex items-center justify-between border-b border-border-subtle pb-4">
        <div>
          <p className="text-xs lowercase text-text-dim">recommended next read</p>
          <h2 className="mt-1 font-serif text-xl font-semibold text-text">Anna Karenina</h2>
        </div>
        <div className="rounded-lg bg-accent-muted px-3 py-2 text-right">
          <p className="text-2xl font-semibold text-text">95%</p>
          <p className="text-xs text-text-muted">match</p>
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-[132px_1fr]">
        <Cover src={coverUrls.anna} title="Anna Karenina" />
        <div className="grid gap-4">
          <div>
            <p className="text-sm font-medium text-text">Why this book</p>
            <p className="mt-2 text-sm leading-6 text-text-muted">
              A strong fit because it connects to books already on your shelf: character-driven,
              reflective, and substantial without guessing from trends.
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-text-dim">Related books</p>
            <ul className="mt-2 grid gap-2 text-sm text-text-muted">
              <li>The Death of Ivan Ilyich</li>
              <li>The Great Gatsby</li>
            </ul>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-border bg-bg-elevated p-3">
              <p className="text-xs text-text-dim">Books Read</p>
              <p className="mt-1 text-xl font-semibold text-text">42</p>
            </div>
            <div className="rounded-lg border border-border bg-bg-elevated p-3">
              <p className="text-xs text-text-dim">Pages Read</p>
              <p className="mt-1 text-xl font-semibold text-text">12.4k</p>
            </div>
            <div className="rounded-lg border border-border bg-bg-elevated p-3">
              <p className="text-xs text-text-dim">Average Rating</p>
              <p className="mt-1 text-xl font-semibold text-text">4.2</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FocusVisual() {
  return (
    <div className="grid gap-4 rounded-lg border border-border bg-surface p-5 shadow-card">
      <div>
        <p className="text-xs font-medium text-text-dim">before</p>
        <div className="mt-3 grid gap-2">
          {["Dune", "Pachinko", "The Nightingale", "Book Lovers", "The Secret History"].map((title) => (
            <div key={title} className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-sm text-text-muted">
              {title}
            </div>
          ))}
        </div>
      </div>
      <div className="h-px bg-border" />
      <div>
        <p className="text-xs font-medium text-text-dim">after</p>
        <div className="mt-3 rounded-lg border border-accent/30 bg-accent-muted p-4">
          <p className="text-sm font-semibold text-text">Read this next</p>
          <p className="mt-1 font-serif text-lg font-semibold text-text">The Nightingale</p>
          <p className="mt-2 text-sm leading-6 text-text-muted">
            A practical pick from the books you already meant to read, based on what you finished
            and rated highly.
          </p>
        </div>
      </div>
    </div>
  );
}

function ExampleRecommendation() {
  return (
    <div className="rounded-lg border border-border bg-surface p-5 shadow-card md:p-6">
      <div className="grid gap-6 md:grid-cols-[160px_1fr]">
        <Cover src={coverUrls.nightingale} title="The Nightingale" />
        <div>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs lowercase text-text-dim">example recommendation</p>
              <h3 className="mt-2 font-serif text-3xl font-semibold text-text">The Nightingale</h3>
            </div>
            <div className="rounded-lg bg-accent-muted px-4 py-3 text-right">
              <p className="text-3xl font-semibold text-text">92%</p>
              <p className="text-xs text-text-muted">match score</p>
            </div>
          </div>
          <div className="mt-5">
            <p className="text-sm font-medium text-text">Why this book</p>
            <p className="mt-2 text-sm leading-6 text-text-muted">
              Recommended from your own shelf signals: historical fiction you rated highly,
              emotionally direct character arcs, and related books already in your library.
            </p>
          </div>
          <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_1fr]">
            <div>
              <p className="text-xs font-medium text-text-dim">Related books</p>
              <div className="mt-3 grid grid-cols-3 gap-3">
                <Cover src={coverUrls.bookThief} title="The Book Thief" />
                <Cover src={coverUrls.pachinko} title="Pachinko" />
                <Cover src={coverUrls.allLight} title="All the Light We Cannot See" />
              </div>
            </div>
            <div>
              <p className="text-xs font-medium text-text-dim">Recommendation breakdown</p>
              <div className="mt-3 grid gap-3">
                {[
                  ["Genre Match", "Very High"],
                  ["Theme Match", "High"],
                  ["Reader Similarity", "Medium"]
                ].map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between rounded-lg border border-border bg-bg-elevated px-3 py-2 text-sm">
                    <span className="text-text-muted">{label}</span>
                    <span className="font-medium text-text">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function LandingPage() {
  return (
    <main className="min-h-screen bg-bg text-text">
      <header className="sticky top-0 z-30 border-b border-border bg-bg/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 lg:px-8">
          <Wordmark to="/" className="text-base sm:text-lg" />
          <nav className="hidden items-center gap-6 text-sm text-text-muted md:flex" aria-label="Landing">
            <a href="#features" className="hover:text-text">Features</a>
            <a href="#how" className="hover:text-text">How It Works</a>
            <a href="#stats" className="hover:text-text">Stats</a>
            <a href="#beta" className="hover:text-text">Open Beta</a>
            <Link to="/login" className="hover:text-text">Sign In</Link>
            <Link to="/register" className="rounded-lg bg-accent px-4 py-2 font-medium text-text shadow-soft hover:bg-accent-dim">
              Get Started
            </Link>
          </nav>
          <Link to="/register" className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-text shadow-soft hover:bg-accent-dim md:hidden">
            Get Started
          </Link>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-10 px-5 pb-20 pt-16 lg:grid-cols-[0.9fr_1.1fr] lg:px-8 lg:pb-28 lg:pt-24">
        <div className="flex flex-col justify-center">
          <p className="text-sm font-medium text-accent-dim">Indie reading tools for your actual shelf.</p>
          <h1 className="mt-5 max-w-3xl font-serif text-5xl font-semibold leading-[1.04] text-text md:text-7xl">
            Stop choosing. Start reading.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-text-muted">
            ShelfTxt helps you pick your next read with transparent recommendations built around your library.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/register" className="rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-text shadow-soft hover:bg-accent-dim">
              Get Started Free
            </Link>
            <a href="#example" className="rounded-lg border border-accent/70 px-5 py-3 text-sm font-semibold text-text hover:bg-accent-muted">
              See Recommendations
            </a>
          </div>
        </div>
        <DashboardVisual />
      </section>

      <section className="border-y border-border bg-bg-elevated/60">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 lg:grid-cols-2 lg:px-8">
          <div className="flex flex-col justify-center">
            <p className="text-sm font-medium text-accent-dim">Problem to solution</p>
            <h2 className="mt-4 font-serif text-4xl font-semibold text-text md:text-5xl">
              You have 137 books on your TBR. Now what?
            </h2>
            <p className="mt-5 max-w-xl text-lg leading-8 text-text-muted">
              Many reading apps help you track books. Few help you choose one.
            </p>
          </div>
          <FocusVisual />
        </div>
      </section>

      <section id="features" className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
        <div className="max-w-2xl">
          <p className="text-sm font-medium text-accent-dim">Features</p>
          <h2 className="mt-4 font-serif text-4xl font-semibold text-text">Built around the next decision.</h2>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <section key={feature.title} className="rounded-lg border border-border bg-surface p-5">
              <h3 className="font-serif text-xl font-semibold text-text">{feature.title}</h3>
              <p className="mt-3 text-sm leading-6 text-text-muted">{feature.body}</p>
            </section>
          ))}
        </div>
      </section>

      <section id="how" className="border-y border-border bg-bg-elevated/60">
        <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <p className="text-sm font-medium text-accent-dim">How It Works</p>
          <h2 className="mt-4 font-serif text-4xl font-semibold text-text">From shelf noise to one clear pick.</h2>
          <div className="mt-10 grid gap-4 md:grid-cols-4">
            {steps.map((step, index) => (
              <div key={step} className="relative rounded-lg border border-border bg-surface p-5">
                <p className="text-sm font-semibold text-accent-dim">Step {index + 1}</p>
                <p className="mt-4 text-lg font-medium text-text">{step}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="example" className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
        <div className="mb-10 max-w-2xl">
          <p className="text-sm font-medium text-accent-dim">Example Recommendation</p>
          <h2 className="mt-4 font-serif text-4xl font-semibold text-text">
            Clear reasons, not black-box guesses.
          </h2>
        </div>
        <ExampleRecommendation />
      </section>

      <section id="stats" className="border-y border-border bg-bg-elevated/60">
        <div className="mx-auto grid max-w-7xl gap-4 px-5 py-16 md:grid-cols-3 lg:px-8">
          {["Personal libraries first", "Transparent recommendations", "Open beta available"].map((metric) => (
            <div key={metric} className="rounded-lg border border-border bg-surface p-6 text-center">
              <p className="text-xl font-semibold text-text">{metric}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="beta" className="mx-auto grid max-w-7xl gap-10 px-5 py-20 lg:grid-cols-[0.8fr_1.2fr] lg:px-8">
        <div>
          <p className="text-sm font-medium text-accent-dim">Built by Readers</p>
          <h2 className="mt-4 font-serif text-4xl font-semibold text-text">Not another feed to maintain.</h2>
        </div>
        <div className="text-lg leading-8 text-text-muted">
          <p>
            ShelfTxt started with a simple problem: having too many books and no idea which one to
            read next.
          </p>
          <p className="mt-5">
            The goal is not to generate summaries, farm engagement, or make your reading feel like
            content. It is to help readers spend less time choosing and more time reading.
          </p>
        </div>
      </section>

      <section className="border-t border-border">
        <div className="mx-auto flex max-w-4xl flex-col items-center px-5 py-20 text-center">
          <h2 className="font-serif text-4xl font-semibold text-text md:text-5xl">
            Ready to pick the next book?
          </h2>
          <p className="mt-5 text-text-muted">Bring the shelf you already have.</p>
          <Link to="/register" className="mt-8 rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-text shadow-soft hover:bg-accent-dim">
            Get Started Free
          </Link>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-8 text-sm text-text-muted md:flex-row md:items-center md:justify-between lg:px-8">
          <Wordmark className="text-sm" />
          <div className="flex flex-wrap gap-4">
            <a href="https://github.com/tranguyeenn/shelftxt" className="hover:text-text">GitHub</a>
            <a href="https://github.com/tranguyeenn/shelftxt/tree/main/docs" className="hover:text-text">Documentation</a>
            <a href="https://github.com/tranguyeenn/shelftxt/blob/main/CHANGELOG.md" className="hover:text-text">Changelog</a>
            <a href="https://github.com/tranguyeenn/shelftxt/blob/main/SECURITY.md" className="hover:text-text">Privacy</a>
            <a href="https://discord.com/" className="hover:text-text">Discord</a>
          </div>
        </div>
      </footer>
    </main>
  );
}
