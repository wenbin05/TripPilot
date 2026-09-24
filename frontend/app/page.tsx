import { TripPlanner } from "@/components/TripPlanner";

export default function Home() {
  return (
    <main>
      <nav className="research-entry" aria-label="Research">
        <a href="/research">Explore live destination research →</a>
      </nav>
      <TripPlanner />
    </main>
  );
}
