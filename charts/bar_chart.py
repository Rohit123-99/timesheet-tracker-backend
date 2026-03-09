import matplotlib
matplotlib.use('QtAgg')

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

class WeeklyChartCanvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        # We use a dark background figure to match the UI theme
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.fig.patch.set_facecolor('#1A1A1A')
        
        self.axes = self.fig.add_subplot(111)
        self.axes.set_facecolor('#1A1A1A')
        
        # Adjust axes colors for dark theme
        self.axes.tick_params(colors='white')
        self.axes.spines['bottom'].set_color('#333333')
        self.axes.spines['left'].set_color('#333333')
        self.axes.spines['top'].set_visible(False)
        self.axes.spines['right'].set_visible(False)

        super().__init__(self.fig)
        self.setParent(parent)

    def plot_weekly_data(self, days, hours):
        self.axes.clear()
        
        # Dark theme axes settings repeated after clear
        self.axes.set_facecolor('#1A1A1A')
        self.axes.tick_params(colors='white')
        self.axes.spines['bottom'].set_color('#333333')
        self.axes.spines['left'].set_color('#333333')
        self.axes.spines['top'].set_visible(False)
        self.axes.spines['right'].set_visible(False)

        # Plot bars
        bars = self.axes.bar(days, hours, color='#5C5CFF', width=0.6, align='center',
                             edgecolor='none', alpha=0.9, zorder=3)
        
        # Add values on top of bars
        for bar in bars:
            yval = bar.get_height()
            self.axes.text(bar.get_x() + bar.get_width()/2, yval + 0.1, f'{yval:.1f}h',
                           ha='center', va='bottom', color='#FFFFFF', fontsize=9)

        # Grid lines behind bars
        self.axes.grid(True, axis='y', color='#333333', linestyle='--', alpha=0.5, zorder=0)
        self.axes.set_ylabel('Hours', color='#AAAAAA')
        
        self.draw()

    def save_light_theme_pdf_chart(self, filename, days, hours):
        """Generates a separate, high-contrast light-themed chart suitable for PDFs."""
        fig = Figure(figsize=(6, 4), dpi=150)
        axes = fig.add_subplot(111)
        axes.set_facecolor('#FFFFFF')
        fig.patch.set_facecolor('#FFFFFF')
        
        axes.tick_params(colors='black')
        axes.spines['bottom'].set_color('#cccccc')
        axes.spines['left'].set_color('#cccccc')
        axes.spines['top'].set_visible(False)
        axes.spines['right'].set_visible(False)

        bars = axes.bar(days, hours, color='#DD2476', width=0.6, align='center', edgecolor='none')
        for bar in bars:
            yval = bar.get_height()
            if yval > 0:
                axes.text(bar.get_x() + bar.get_width()/2, yval + 0.1, f'{yval:.1f}h',
                               ha='center', va='bottom', color='black', fontsize=9, fontweight='bold')
        
        axes.grid(True, axis='y', color='#eeeeee', linestyle='--')
        axes.set_ylabel('Hours', color='#333333', fontweight='bold')
        fig.tight_layout()
        fig.savefig(filename, facecolor='#FFFFFF', bbox_inches='tight')

