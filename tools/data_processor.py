import os
import shutil
import subprocess
import logging
import pandas as pd

logger = logging.getLogger(__name__)


class DataProcessorTool:
    """
    Data Processing Tool for CSV/Excel data analysis and FFmpeg media converting/trimming.
    """

    def read_analyze_csv_excel(self, file_path: str) -> str:
        """
        Reads CSV or Excel file and returns statistical summary, column types, and sample rows.
        """
        if not file_path or not os.path.exists(file_path):
            return f"File not found: {file_path}"

        try:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in (".csv", ".txt"):
                df = pd.read_csv(file_path)
            elif ext in (".xlsx", ".xls"):
                df = pd.read_excel(file_path)
            else:
                return f"Unsupported data file extension '{ext}'. Only CSV and Excel files are supported."

            summary = [
                f"Data File Summary for '{os.path.basename(file_path)}':",
                f"- Total Rows: {len(df)} | Total Columns: {len(df.columns)}",
                f"- Columns: {list(df.columns)}",
                "\nData Preview (First 3 rows):",
                df.head(3).to_string(),
            ]
            return "\n".join(summary)
        except Exception as e:
            return f"Error analyzing data file '{file_path}': {e}"

    def convert_trim_media(
        self,
        input_file: str,
        output_file: str,
        start_time: str = None,
        end_time: str = None,
    ) -> str:
        """
        Trims or converts audio/video media files using FFmpeg.

        Args:
            input_file (str): Path to input media file.
            output_file (str): Path for output converted/trimmed media.
            start_time (str, optional): Start timestamp (e.g. '00:00:10').
            end_time (str, optional): End timestamp or duration.

        Returns:
            str: Confirmation string.
        """
        if not input_file or not os.path.exists(input_file):
            return f"Input media file not found: {input_file}"

        ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"
        cmd = [ffmpeg_path, "-y", "-i", input_file]

        if start_time:
            cmd.extend(["-ss", str(start_time)])
        if end_time:
            cmd.extend(["-to", str(end_time)])

        cmd.append(output_file)

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate(timeout=30)
            if proc.returncode == 0 and os.path.exists(output_file):
                return f"Successfully processed media file to '{output_file}'."
            return f"Media processing failed: {stderr.decode('utf-8', errors='ignore')[:200]}"
        except Exception as e:
            return f"FFmpeg execution error: {e}"


# Helper functions
def analyze_data_file(file_path: str) -> str:
    return DataProcessorTool().read_analyze_csv_excel(file_path)


def trim_media_file(input_file: str, output_file: str, start_time: str = None, end_time: str = None) -> str:
    return DataProcessorTool().convert_trim_media(input_file, output_file, start_time, end_time)


if __name__ == "__main__":
    tool = DataProcessorTool()
    print("[DataProcessorTool] Loaded successfully.")
