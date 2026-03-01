"""
Log viewer API views for strategy execution logs.
"""
import os
from pathlib import Path
from datetime import datetime

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated


class LogFilesListView(APIView):
    """
    API endpoint to list all available log files for a user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all log files in the logs/users directory."""
        try:
            logs_dir = os.path.join(settings.BASE_DIR, 'logs', 'users')
            
            if not os.path.exists(logs_dir):
                return Response({
                    'files': [],
                    'message': 'No logs directory found'
                })

            log_files = []
            for filename in os.listdir(logs_dir):
                if filename.endswith('.log'):
                    filepath = os.path.join(logs_dir, filename)
                    file_stat = os.stat(filepath)
                    
                    log_files.append({
                        'filename': filename,
                        'username': filename.replace('_strategy.log', ''),
                        'size': file_stat.st_size,
                        'size_mb': round(file_stat.st_size / (1024 * 1024), 2),
                        'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                        'modified_display': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            # Sort by modified time, most recent first
            log_files.sort(key=lambda x: x['modified'], reverse=True)
            
            return Response({
                'files': log_files,
                'count': len(log_files)
            })
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LogFileContentView(APIView):
    """
    API endpoint to retrieve contents of a specific log file.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Get log file contents.
        Query params:
        - filename: Name of the log file
        - lines: Number of lines to retrieve (default: 500, max: 5000)
        - tail: If true, get last N lines; if false, get first N lines
        """
        try:
            filename = request.query_params.get('filename')
            if not filename:
                return Response({
                    'error': 'Filename parameter is required'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Security: Prevent directory traversal
            if '..' in filename or '/' in filename or '\\' in filename:
                return Response({
                    'error': 'Invalid filename'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logs_dir = os.path.join(settings.BASE_DIR, 'logs', 'users')
            filepath = os.path.join(logs_dir, filename)
            
            if not os.path.exists(filepath):
                return Response({
                    'error': 'Log file not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get query parameters
            lines = min(int(request.query_params.get('lines', 500)), 5000)
            tail = request.query_params.get('tail', 'true').lower() == 'true'
            
            # Read file
            with open(filepath, 'r') as f:
                if tail:
                    # Get last N lines
                    content_lines = self._tail_file(f, lines)
                else:
                    # Get first N lines
                    content_lines = [f.readline() for _ in range(lines)]
            
            # Get file metadata
            file_stat = os.stat(filepath)
            
            return Response({
                'filename': filename,
                'content': ''.join(content_lines),
                'lines_returned': len(content_lines),
                'size': file_stat.st_size,
                'size_mb': round(file_stat.st_size / (1024 * 1024), 2),
                'modified': datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                'modified_display': datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
            
        except Exception as e:
            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _tail_file(self, f, n):
        """Read last n lines from file efficiently."""
        # For small n, just read all and return last n
        lines = f.readlines()
        return lines[-n:] if len(lines) > n else lines
