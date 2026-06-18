import { Link } from "react-router-dom";

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
    title: "Explainable Recommendations",
    body: "Not just \"because the algorithm said so.\" See exactly why a book was recommended and which books influenced the suggestion."
  },
  {
    title: "Library Management",
    body: "Track Want to Read, Reading, Completed, and DNF without turning your shelf into busywork."
  },
  {
    title: "Reading Statistics",
    body: "Visualize books per month, pages read, ratings, and reading trends from your own library."
  },
  {
    title: "Reader Profiles",
    body: "Customize reading goals, favorite genres, and the library signals that shape your next pick."
  },
  {
    title: "Open Source",
    body: "Built publicly and continuously improved with reader feedback."
  },
  {
    title: "Privacy First",
    body: "Your reading data belongs to you. ShelfTxt is built around personal libraries, not ad targeting."
  }
];

const steps = [
  "Import or add books.",
  "Rate and track what you read.",
  "ShelfTxt learns your preferences.",
  "Get recommendations with real explanations."
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
    <div className="rounded-lg border border-border bg-surface p-4 shadow-2xl shadow-black/40 sm:p-5">
      <div className="mb-4 flex items-center justify-between border-b border-border-subtle pb-4">
        <div>
          <p className="text-xs lowercase tracking-wide text-text-dim">recommended next read</p>
          <h2 className="mt-1 text-lg font-semibold text-text">Anna Karenina</h2>
        </div>
        <div className="rounded-lg bg-accent-muted px-3 py-2 text-right">
          <p className="text-2xl font-semibold text-accent">95%</p>
          <p className="text-xs text-text-muted">match</p>
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-[132px_1fr]">
        <Cover src={coverUrls.anna} title="Anna Karenina" />
        <div className="grid gap-4">
          <div>
            <p className="text-sm font-medium text-text">Why this book</p>
            <p className="mt-2 text-sm leading-6 text-text-muted">
              Because you enjoyed The Death of Ivan Ilyich and The Great Gatsby, you may enjoy
              another character-driven literary classic exploring relationships, society, and
              personal growth.
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
    <div className="grid gap-4 rounded-lg border border-border bg-surface p-5 shadow-xl shadow-black/30">
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
          <p className="mt-1 text-lg font-semibold text-accent">The Nightingale</p>
          <p className="mt-2 text-sm leading-6 text-text-muted">
            Strong historical fiction match based on books you finished and rated highly.
          </p>
        </div>
      </div>
    </div>
  );
}

function ExampleRecommendation() {
  return (
    <div className="rounded-lg border border-border bg-surface p-5 shadow-2xl shadow-black/30 md:p-6">
      <div className="grid gap-6 md:grid-cols-[160px_1fr]">
        <Cover src={coverUrls.nightingale} title="The Nightingale" />
        <div>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs lowercase tracking-wide text-text-dim">example recommendation</p>
              <h3 className="mt-2 text-2xl font-semibold text-text">The Nightingale</h3>
            </div>
            <div className="rounded-lg bg-accent-muted px-4 py-3 text-right">
              <p className="text-3xl font-semibold text-accent">92%</p>
              <p className="text-xs text-text-muted">match score</p>
            </div>
          </div>
          <div className="mt-5">
            <p className="text-sm font-medium text-text">Why this book</p>
            <p className="mt-2 text-sm leading-6 text-text-muted">
              Because you rated The Book Thief highly and frequently enjoy historical fiction with
              strong emotional character arcs.
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
    <main className="min-h-screen bg-[#111111] text-text">
      <header className="sticky top-0 z-30 border-b border-border bg-[#111111]/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 lg:px-8">
          <Link to="/" className="text-lg font-semibold tracking-tight text-text">
            ShelfTxt
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-text-muted md:flex" aria-label="Landing">
            <a href="#features" className="hover:text-text">Features</a>
            <a href="#how" className="hover:text-text">How It Works</a>
            <a href="#stats" className="hover:text-text">Stats</a>
            <a href="#beta" className="hover:text-text">Open Beta</a>
            <Link to="/login" className="hover:text-text">Sign In</Link>
            <Link to="/register" className="rounded-lg bg-accent px-4 py-2 font-medium text-bg hover:bg-accent-dim">
              Get Started
            </Link>
          </nav>
          <Link to="/register" className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-bg hover:bg-accent-dim md:hidden">
            Get Started
          </Link>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-10 px-5 pb-20 pt-16 lg:grid-cols-[0.9fr_1.1fr] lg:px-8 lg:pb-28 lg:pt-24">
        <div className="flex flex-col justify-center">
          <p className="text-sm font-medium text-accent">You have too many books.</p>
          <h1 className="mt-5 max-w-3xl text-5xl font-semibold leading-[1.04] tracking-tight text-text md:text-7xl">
            Stop wondering what to read next.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-text-muted">
            ShelfTxt analyzes your library, reading habits, ratings, and preferences to recommend
            the next book you'll actually want to pick up.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/register" className="rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-bg hover:bg-accent-dim">
              Get Started Free
            </Link>
            <a href="#example" className="rounded-lg border border-border px-5 py-3 text-sm font-semibold text-text hover:border-accent">
              See Recommendations
            </a>
          </div>
        </div>
        <DashboardVisual />
      </section>

      <section className="border-y border-border bg-bg-elevated/60">
        <div className="mx-auto grid max-w-7xl gap-10 px-5 py-20 lg:grid-cols-2 lg:px-8">
          <div className="flex flex-col justify-center">
            <p className="text-sm font-medium text-accent">Problem to solution</p>
            <h2 className="mt-4 text-4xl font-semibold tracking-tight text-text md:text-5xl">
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
          <p className="text-sm font-medium text-accent">Features</p>
          <h2 className="mt-4 text-4xl font-semibold tracking-tight text-text">Built around the next decision.</h2>
        </div>
        <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <section key={feature.title} className="rounded-lg border border-border bg-surface p-5">
              <h3 className="text-lg font-semibold text-text">{feature.title}</h3>
              <p className="mt-3 text-sm leading-6 text-text-muted">{feature.body}</p>
            </section>
          ))}
        </div>
      </section>

      <section id="how" className="border-y border-border bg-bg-elevated/60">
        <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
          <p className="text-sm font-medium text-accent">How It Works</p>
          <h2 className="mt-4 text-4xl font-semibold tracking-tight text-text">From shelf noise to one clear pick.</h2>
          <div className="mt-10 grid gap-4 md:grid-cols-4">
            {steps.map((step, index) => (
              <div key={step} className="relative rounded-lg border border-border bg-surface p-5">
                <p className="text-sm font-semibold text-accent">Step {index + 1}</p>
                <p className="mt-4 text-lg font-medium text-text">{step}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="example" className="mx-auto max-w-7xl px-5 py-20 lg:px-8">
        <div className="mb-10 max-w-2xl">
          <p className="text-sm font-medium text-accent">Example Recommendation</p>
          <h2 className="mt-4 text-4xl font-semibold tracking-tight text-text">
            Explanations that sound like a reader, not a formula.
          </h2>
        </div>
        <ExampleRecommendation />
      </section>

      <section id="stats" className="border-y border-border bg-bg-elevated/60">
        <div className="mx-auto grid max-w-7xl gap-4 px-5 py-16 md:grid-cols-3 lg:px-8">
          {["Thousands of books tracked", "Hundreds of recommendations generated", "Open Beta Available"].map((metric) => (
            <div key={metric} className="rounded-lg border border-border bg-surface p-6 text-center">
              <p className="text-xl font-semibold text-text">{metric}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="beta" className="mx-auto grid max-w-7xl gap-10 px-5 py-20 lg:grid-cols-[0.8fr_1.2fr] lg:px-8">
        <div>
          <p className="text-sm font-medium text-accent">Built by Readers</p>
          <h2 className="mt-4 text-4xl font-semibold tracking-tight text-text">Not another Goodreads clone.</h2>
        </div>
        <div className="text-lg leading-8 text-text-muted">
          <p>
            ShelfTxt started with a simple problem: having too many books and no idea which one to
            read next.
          </p>
          <p className="mt-5">
            The goal is not to build another social shelf. The goal is to help readers spend less
            time choosing and more time reading.
          </p>
        </div>
      </section>

      <section className="border-t border-border">
        <div className="mx-auto flex max-w-4xl flex-col items-center px-5 py-20 text-center">
          <h2 className="text-4xl font-semibold tracking-tight text-text md:text-5xl">
            Ready to find your next favorite book?
          </h2>
          <p className="mt-5 text-text-muted">No credit card required.</p>
          <Link to="/register" className="mt-8 rounded-lg bg-accent px-5 py-3 text-sm font-semibold text-bg hover:bg-accent-dim">
            Get Started Free
          </Link>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-8 text-sm text-text-muted md:flex-row md:items-center md:justify-between lg:px-8">
          <p>ShelfTxt</p>
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
