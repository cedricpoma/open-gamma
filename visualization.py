"""
SPX Options Gamma/Charm Visualization
Creates the three-panel visualization for market maker exposure analysis
Professional Dark Mode Style with 3D Support
"""

import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# Set dark style for static plots
plt.style.use('dark_background')

class OptionsVisualizer:
    def __init__(self, spx_data):
        self.spx_data = spx_data
        self.greeks_df = None
        self.exposure_df = None

    def prepare_data(self):
        """Prepare Greeks and exposure data"""
        if self.spx_data.options_data is None:
            self.spx_data.fetch_options_data()

        if self.spx_data.options_data is not None:
            self.greeks_df = self.spx_data.calculate_greeks()
            self.exposure_df = self.spx_data.get_market_maker_exposure(self.greeks_df)

    def create_interactive_dashboard(self):
        """
        Create interactive dashboard using plotly (Professional Dark Theme)
        """
        if self.greeks_df is None:
            self.prepare_data()

        # Generate data first to get the unified price grid and focus
        gamma_data = self.spx_data.get_gamma_surface(self.greeks_df)
        
        # Determine focus point (Use Data Center if Spot is far off)
        spot = self.spx_data.spot_price if self.spx_data.spot_price else (gamma_data.get('center_strike', 5500) if gamma_data else 5500)
        center_focus = spot
        
        if gamma_data:
            data_center = gamma_data.get('center_strike', spot)
            # If spot is > 10% away from data center, use data center (Data mismatch case)
            if spot and abs(spot - data_center) / data_center > 0.10:
                center_focus = data_center
                print(f"Notice: Focusing dashboard on Data Center (${data_center:.0f}) instead of Spot (${spot:.0f})")

        fig = make_subplots(
            rows=1, cols=3,
            subplot_titles=('<b>GAMMA EXPOSURE</b><br>Intraday Evolution', 
                           '<b>NET GEX</b><br>Strike Breakdown', 
                           '<b>CHARM EXPOSURE</b><br>Intraday Evolution'),
            specs=[[{"type": "xy"}, {"type": "xy"}, {"type": "xy"}]],
            horizontal_spacing=0.05,
            shared_yaxes=True 
        )

        # Define Background Colors
        paper_bg_color = '#F2F4F7' # Outer background (Light Gray)
        plot_bg_color = '#FFFFFF'  # Inner window background (White)

        # -------------------------------------------------------------
        # PANEL 1: GAMMA HEATMAP (Light Mode)
        # -------------------------------------------------------------
        if gamma_data:
            z_val = gamma_data['gamma_surface'].T
            z_max = np.abs(z_val).max()
            
            fig.add_trace(
                go.Heatmap(
                    z=z_val,
                    x=gamma_data['times'], # Hours into future
                    y=gamma_data['prices'],
                    colorscale=[
                        [0.0, '#FF4444'],   # Red/Orange (Short GEX)
                        [0.5, plot_bg_color], # Matches Window Background (White)
                        [1.0, '#0088FF']    # Deep Blue (Long GEX)
                    ],
                    zsmooth='best', # Smooth clouds
                    zmin=-z_max,
                    zmax=z_max,
                    showscale=False,
                    hovertemplate='Time: +%{x:.1f}h<br>Price: $%{y:.0f}<br>Gamma: %{z:.2e}<extra></extra>',
                    name='Gamma'
                ),
                row=1, col=1
            )
            # Add Spot Line
            fig.add_hline(y=center_focus, line_dash="dash", line_color="black", row=1, col=1, opacity=0.5)

        # -------------------------------------------------------------
        # PANEL 2: STRIKE BREAKDOWN (Center)
        # -------------------------------------------------------------
        if self.exposure_df is not None and not self.exposure_df.empty:
            center_df = self.exposure_df.copy()
            # Zoom logic: Focus around the DETERMINED center, not just spot
            center_df = center_df[
                (center_df['strike'] >= center_focus * 0.90) & 
                (center_df['strike'] <= center_focus * 1.10)
            ]
            
            pos_mask = center_df['gamma'] >= 0
            neg_mask = center_df['gamma'] < 0
            
            fig.add_trace(
                go.Bar(
                    x=center_df[pos_mask]['gamma'],
                    y=center_df[pos_mask]['strike'],
                    orientation='h',
                    marker_color='#0088FF',
                    name='Long Gamma'
                ),
                row=1, col=2
            )
            
            fig.add_trace(
                go.Bar(
                    x=center_df[neg_mask]['gamma'],
                    y=center_df[neg_mask]['strike'],
                    orientation='h',
                    marker_color='#FF4444',
                    name='Short Gamma'
                ),
                row=1, col=2
            )
            fig.add_hline(y=center_focus, line_dash="dash", line_color="black", row=1, col=2)

        # -------------------------------------------------------------
        # PANEL 3: CHARM HEATMAP (Light Mode)
        # -------------------------------------------------------------
        # Pass the unified price grid to Charm so they match
        price_grid = gamma_data['prices'] if gamma_data else None
        charm_data = self.create_charm_surface_data(self.exposure_df, price_grid)
        
        if charm_data:
             z_val_charm = charm_data['surface'].T
             z_max_charm = np.abs(z_val_charm).max()

             fig.add_trace(
                go.Heatmap(
                    z=z_val_charm,
                    x=charm_data['times'],
                    y=charm_data['prices'],
                    colorscale=[
                         [0.0, '#FFD700'],   # Gold/Orange (Negative Charm)
                         [0.5, plot_bg_color], # Matches Window Background (White)
                         [1.0, '#00CED1']    # Dark Turquoise (Positive Charm)
                    ],
                    zsmooth='best',
                    zmin=-z_max_charm,
                    zmax=z_max_charm,
                    showscale=False,
                    hovertemplate='Time: +%{x:.1f}h<br>Price: $%{y:.0f}<br>Charm: %{z:.2e}<extra></extra>',
                    name='Charm'
                ),
                row=1, col=3
            )
            # Add Spot Line
             fig.add_hline(y=center_focus, line_dash="dash", line_color="black", row=1, col=3, opacity=0.5)

        # -------------------------------------------------------------
        # LAYOUT (Gray Background, White Windows)
        # -------------------------------------------------------------
        title_text = f'<b>SPX OPTIONALITY DEPTH</b> | Center: {center_focus:.0f}' if center_focus else '<b>SPX OPTIONALITY DEPTH</b>'
        
        fig.update_layout(
            template='plotly_white',
            title=dict(text=title_text, x=0.5, font=dict(size=24)),
            height=800,
            showlegend=False,
            paper_bgcolor=paper_bg_color,  # Outer background Light Gray
            plot_bgcolor=plot_bg_color,    # Inner window background White
            margin=dict(l=50, r=50, t=80, b=50),
            font=dict(family="Roboto Mono, monospace", color="black")
        )
        
        # Shared Y axes settings
        grid_color = '#E5E5E5' # Lighter grid for white background
        fig.update_xaxes(title_text="Hours Forward", gridcolor=grid_color)
        fig.update_xaxes(title_text="Net GEX", row=1, col=2, gridcolor=grid_color)
        fig.update_yaxes(title_text="Price", row=1, col=1, gridcolor=grid_color)
        fig.update_yaxes(showticklabels=False, row=1, col=2, gridcolor=grid_color) 
        fig.update_yaxes(showticklabels=False, row=1, col=3, gridcolor=grid_color) 

        return fig

    def create_charm_surface_data(self, exposure_df, price_grid=None):
        """
        Create a synthetic Charm surface based on current exposure.
        Matches Gamma surface logic (Time Decay Fingers).
        """
        if exposure_df is None or exposure_df.empty:
            return None
            
        # Use provided price grid or generate one (fallback)
        if price_grid is not None:
             prices = price_grid
        else:
             # Fallback logic
             spot = self.spx_data.spot_price if self.spx_data.spot_price else 5500.0
             prices = np.linspace(spot * 0.95, spot * 1.05, 150)

        times = np.linspace(0, 6.5, 50)
        
        # Optimize loop
        grid_min = prices.min()
        grid_max = prices.max()
        relevant_exposure = exposure_df[
            (exposure_df['strike'] >= grid_min * 0.9) & 
            (exposure_df['strike'] <= grid_max * 1.1)
        ]
        
        surface = []
        base_width_pct = 0.003
        
        strikes = relevant_exposure['strike'].values
        charms = relevant_exposure['charm'].values

        for t in times:
             # Decay factor for fingers (same as gamma)
             t_norm = t / 6.5
             width_decay = 1.0 - (0.7 * t_norm)
             
             row_data = []
             for p in prices:
                 width = p * base_width_pct * width_decay
                 
                 deltas = (p - strikes)
                 gaussians = np.exp(-0.5 * (deltas / width)**2)
                 
                 val = np.sum(charms * gaussians)
                 row_data.append(val)
             surface.append(row_data)
             
        return {
            'prices': prices,
            'times': times,
            'surface': np.array(surface)
        }

    def create_combined_dashboard(self, save_path=None):
        """
        Static Matplotlib fallback (Dark Mode)
        """
        self.prepare_data()
        
        fig = plt.figure(figsize=(20, 8), facecolor='black')
        gs = fig.add_gridspec(1, 3, width_ratios=[1, 0.8, 1], wspace=0.1)
        
        # Panel 1: Gamma Heatmap
        ax1 = fig.add_subplot(gs[0, 0])
        ax1.set_facecolor('black')
        gamma_data = self.spx_data.get_gamma_surface(self.greeks_df)
        if gamma_data:
            im1 = ax1.imshow(gamma_data['gamma_surface'].T, aspect='auto', origin='lower',
                           extent=[0, 6.5, gamma_data['prices'].min(), gamma_data['prices'].max()],
                           cmap='seismic_r') 
            ax1.set_title('Gamma Heatmap', color='white', fontweight='bold')
            ax1.tick_params(colors='white')
            
        # Panel 2: Strike Breakdown
        ax2 = fig.add_subplot(gs[0, 1])
        ax2.set_facecolor('black')
        if self.exposure_df is not None:
            colors = ['#0088FF' if g > 0 else '#FF3333' for g in self.exposure_df['gamma']]
            ax2.barh(self.exposure_df['strike'], self.exposure_df['gamma'], color=colors)
            ax2.axvline(0, color='white', linewidth=0.5)
            ax2.set_title('Strike Breakdown', color='white', fontweight='bold')
            ax2.tick_params(colors='white')

        # Main Title
        fig.suptitle(f"SPX Options Analysis | Spot: {self.spx_data.spot_price:.0f}", 
                    color='white', fontsize=16, fontweight='bold', y=0.95)

        if save_path:
            plt.savefig(save_path, facecolor='black', edgecolor='none')
        
        return fig

if __name__ == "__main__":
    from options_data import SPXOptionsData
    spx = SPXOptionsData()
    viz = OptionsVisualizer(spx)
    viz.create_interactive_dashboard().show()