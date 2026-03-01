import { useEffect, useState } from "react";
import { API_BASE_URL } from "../utils/constants";

export default function LogsViewerPage() {
  const [logFiles, setLogFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [logContent, setLogContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lines, setLines] = useState(500);
  const [autoRefresh, setAutoRefresh] = useState(false);

  // Fetch list of log files
  const fetchLogFiles = async () => {
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        setError("Not authenticated. Please login first.");
        return;
      }

      const response = await fetch(`${API_BASE_URL}/logs/files/`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error("Failed to fetch log files");
      }

      const data = await response.json();
      setLogFiles(data.files || []);
    } catch (err) {
      setError(err.message);
    }
  };

  // Fetch content of selected log file
  const fetchLogContent = async (filename) => {
    if (!filename) return;

    setLoading(true);
    setError(null);

    try {
      const token = localStorage.getItem("token");
      const response = await fetch(
        `${API_BASE_URL}/logs/content/?filename=${filename}&lines=${lines}&tail=true`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error("Failed to fetch log content");
      }

      const data = await response.json();
      setLogContent(data.content || "");
      setSelectedFile({
        filename: data.filename,
        size_mb: data.size_mb,
        modified_display: data.modified_display,
        lines_returned: data.lines_returned,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchLogFiles();
  }, []);

  // Auto-refresh
  useEffect(() => {
    if (autoRefresh && selectedFile) {
      const interval = setInterval(() => {
        fetchLogContent(selectedFile.filename);
      }, 5000); // Refresh every 5 seconds

      return () => clearInterval(interval);
    }
  }, [autoRefresh, selectedFile]);

  const handleFileSelect = (filename) => {
    fetchLogContent(filename);
  };

  const handleRefresh = () => {
    if (selectedFile) {
      fetchLogContent(selectedFile.filename);
    }
    fetchLogFiles();
  };

  const handleLinesChange = (e) => {
    const newLines = parseInt(e.target.value);
    setLines(newLines);
    if (selectedFile) {
      fetchLogContent(selectedFile.filename);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold mb-2">Strategy Execution Logs</h1>
          <p className="text-gray-400">
            View detailed execution logs for each user's trading strategy
          </p>
        </div>

        {error && (
          <div className="bg-red-900/50 border border-red-600 text-red-200 px-4 py-3 rounded mb-6">
            <p className="font-medium">Error</p>
            <p className="text-sm">{error}</p>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar - Log Files List */}
          <div className="lg:col-span-1">
            <div className="bg-gray-800 rounded-lg shadow-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">Log Files</h2>
                <button
                  onClick={fetchLogFiles}
                  className="text-blue-400 hover:text-blue-300 text-sm"
                >
                  Refresh
                </button>
              </div>

              {logFiles.length === 0 ? (
                <p className="text-gray-400 text-sm">No log files found</p>
              ) : (
                <div className="space-y-2">
                  {logFiles.map((file) => (
                    <button
                      key={file.filename}
                      onClick={() => handleFileSelect(file.filename)}
                      className={`w-full text-left p-3 rounded transition ${
                        selectedFile?.filename === file.filename
                          ? "bg-blue-600 text-white"
                          : "bg-gray-700 hover:bg-gray-600 text-gray-200"
                      }`}
                    >
                      <div className="font-medium text-sm truncate">
                        {file.username}
                      </div>
                      <div className="text-xs text-gray-400 mt-1">
                        {file.size_mb} MB
                      </div>
                      <div className="text-xs text-gray-400">
                        {file.modified_display}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Main Content - Log Viewer */}
          <div className="lg:col-span-3">
            <div className="bg-gray-800 rounded-lg shadow-lg p-4">
              {/* Controls */}
              <div className="flex items-center justify-between mb-4 flex-wrap gap-4">
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <label className="text-sm text-gray-400">Lines:</label>
                    <select
                      value={lines}
                      onChange={handleLinesChange}
                      className="bg-gray-700 text-white px-3 py-1 rounded border border-gray-600 text-sm"
                    >
                      <option value={100}>100</option>
                      <option value={500}>500</option>
                      <option value={1000}>1000</option>
                      <option value={2000}>2000</option>
                      <option value={5000}>5000</option>
                    </select>
                  </div>

                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={autoRefresh}
                      onChange={(e) => setAutoRefresh(e.target.checked)}
                      className="rounded"
                    />
                    <span className="text-gray-400">Auto-refresh (5s)</span>
                  </label>
                </div>

                <button
                  onClick={handleRefresh}
                  disabled={!selectedFile}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded text-sm font-medium transition"
                >
                  Refresh
                </button>
              </div>

              {/* File Info */}
              {selectedFile && (
                <div className="bg-gray-700 rounded p-3 mb-4 text-sm">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <span className="text-gray-400">File:</span>
                      <span className="ml-2 font-medium">
                        {selectedFile.filename}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">Size:</span>
                      <span className="ml-2 font-medium">
                        {selectedFile.size_mb} MB
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">Modified:</span>
                      <span className="ml-2 font-medium">
                        {selectedFile.modified_display}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400">Lines:</span>
                      <span className="ml-2 font-medium">
                        {selectedFile.lines_returned}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Log Content */}
              <div className="bg-gray-900 rounded-lg p-4 min-h-[600px] max-h-[800px] overflow-auto">
                {loading ? (
                  <div className="flex items-center justify-center h-full">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                  </div>
                ) : logContent ? (
                  <pre className="text-xs font-mono text-gray-300 whitespace-pre-wrap">
                    {logContent}
                  </pre>
                ) : (
                  <div className="flex items-center justify-center h-full text-gray-500">
                    <div className="text-center">
                      <svg
                        className="mx-auto h-12 w-12 text-gray-600"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                        />
                      </svg>
                      <p className="mt-2">Select a log file to view its contents</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
