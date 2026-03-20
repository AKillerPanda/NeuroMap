import { Link } from "react-router";
import { Button } from "../components/ui/button";
import { Brain } from "lucide-react";

export function NotFound() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-violet-50 via-white to-blue-50 flex items-center justify-center">
      <div className="text-center">
        <Brain className="size-16 mx-auto mb-4 text-gray-300" />
        <h1 className="text-4xl font-bold mb-2">404</h1>
        <h2 className="font-semibold mb-2">Page Not Found</h2>
        <p className="text-gray-600 mb-6">
          The page you're looking for doesn't exist in this knowledge graph.
        </p>
        <Link to="/">
          <Button className="bg-violet-600 hover:bg-violet-700">Go Home</Button>
        </Link>
      </div>
    </div>
  );
}
