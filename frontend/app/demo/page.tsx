import { TripPlanner } from "@/components/TripPlanner";
import Link from "next/link";

export default function Demo() {
  return (
    <main>
      <nav className="research-entry">
        <Link href="/">Back to live planner</Link>
      </nav>
      <TripPlanner />
    </main>
  );
}
