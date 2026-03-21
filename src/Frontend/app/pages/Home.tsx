import { Link } from "react-router";
import { Network, Route, Sparkles } from "lucide-react";
import { Button } from "../components/ui/button";
import { NeuroMapLogo } from "../components/NeuroMapLogo";

export function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-violet-50 via-white to-blue-50">
      <div className="container mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-16">
          <div className="flex items-center justify-center gap-3 mb-6">
            <NeuroMapLogo className="size-12" />
            <h1 className="text-5xl font-bold bg-gradient-to-r from-violet-600 to-blue-600 bg-clip-text text-transparent">
              NeuroMap
            </h1>
          </div>
          <p className="text-xl text-gray-600 max-w-2xl mx-auto">
            Transform any set of subjects into a dynamic topological knowledge graph.
            Learn smarter with AI-powered connections and guided learning paths.
          </p>
        </div>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-8 mb-16 max-w-5xl mx-auto">
          <div className="bg-white rounded-2xl p-6 shadow-lg border border-violet-100">
            <div className="bg-violet-100 w-12 h-12 rounded-xl flex items-center justify-center mb-4">
              <Network className="size-6 text-violet-600" />
            </div>
            <h3 className="font-semibold mb-2">Interactive Knowledge Graph</h3>
            <p className="text-gray-600">
              Visualize how concepts interconnect with a dynamic, navigable network of topics and relationships.
            </p>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-lg border border-blue-100">
            <div className="bg-blue-100 w-12 h-12 rounded-xl flex items-center justify-center mb-4">
              <Route className="size-6 text-blue-600" />
            </div>
            <h3 className="font-semibold mb-2">Guided Learning Paths</h3>
            <p className="text-gray-600">
              Get personalized recommendations on what to learn next based on prerequisites and your progress.
            </p>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-lg border border-emerald-100">
            <div className="bg-emerald-100 w-12 h-12 rounded-xl flex items-center justify-center mb-4">
              <Sparkles className="size-6 text-emerald-600" />
            </div>
            <h3 className="font-semibold mb-2">Smart Connections</h3>
            <p className="text-gray-600">
              Discover hidden relationships between topics, revealing prerequisite chains and conceptual overlaps.
            </p>
          </div>
        </div>

        {/* Key Features List */}
        <div className="bg-white rounded-2xl p-8 max-w-3xl mx-auto mb-12 shadow-lg">
          <h2 className="font-semibold mb-6 text-center">What NeuroMap Reveals</h2>
          <div className="grid md:grid-cols-2 gap-4">
            <div className="flex items-start gap-3">
              <div className="bg-violet-100 rounded-lg p-2 mt-0.5">
                <div className="size-2 bg-violet-600 rounded-full" />
              </div>
              <div>
                <p className="font-medium">Prerequisite Relationships</p>
                <p className="text-sm text-gray-600">What you need to learn first</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="bg-blue-100 rounded-lg p-2 mt-0.5">
                <div className="size-2 bg-blue-600 rounded-full" />
              </div>
              <div>
                <p className="font-medium">Conceptual Overlaps</p>
                <p className="text-sm text-gray-600">Topics that share common ground</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="bg-emerald-100 rounded-lg p-2 mt-0.5">
                <div className="size-2 bg-emerald-600 rounded-full" />
              </div>
              <div>
                <p className="font-medium">Hierarchical Structures</p>
                <p className="text-sm text-gray-600">From basics to advanced concepts</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="bg-orange-100 rounded-lg p-2 mt-0.5">
                <div className="size-2 bg-orange-600 rounded-full" />
              </div>
              <div>
                <p className="font-medium">Cross-Disciplinary Links</p>
                <p className="text-sm text-gray-600">Connections between different fields</p>
              </div>
            </div>
          </div>
        </div>

        {/* CTA */}
        <div className="text-center">
          <Link to="/workspace">
            <Button size="lg" className="bg-violet-600 hover:bg-violet-700 text-white px-8">
              Start Building Your Knowledge Graph
            </Button>
          </Link>
          <p className="text-sm text-gray-500 mt-4">
            No account required • Free to use • Build unlimited graphs
          </p>
        </div>

        {/* How it Works */}
        <div className="mt-16 max-w-4xl mx-auto">
          <h2 className="font-semibold text-center mb-8">How NeuroMap Works</h2>
          <div className="grid md:grid-cols-3 gap-8">
            <div className="text-center">
              <div className="bg-violet-600 text-white size-12 rounded-full flex items-center justify-center mx-auto mb-4 text-xl font-bold">
                1
              </div>
              <h3 className="font-medium mb-2">Add Your Topics</h3>
              <p className="text-sm text-gray-600">
                Input subjects you want to study with their categories and difficulty levels
              </p>
            </div>
            <div className="text-center">
              <div className="bg-blue-600 text-white size-12 rounded-full flex items-center justify-center mx-auto mb-4 text-xl font-bold">
                2
              </div>
              <h3 className="font-medium mb-2">Generate Connections</h3>
              <p className="text-sm text-gray-600">
                Our AI analyzes relationships and creates a knowledge graph automatically
              </p>
            </div>
            <div className="text-center">
              <div className="bg-emerald-600 text-white size-12 rounded-full flex items-center justify-center mx-auto mb-4 text-xl font-bold">
                3
              </div>
              <h3 className="font-medium mb-2">Follow Your Path</h3>
              <p className="text-sm text-gray-600">
                Get a personalized learning sequence based on prerequisites and difficulty
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}