#!/usr/bin/env python3
"""
Flight Analysis by Squawk Code

Módulo para analizar cantidad de vuelos por código Squawk,
considerando la velocidad de rotación de antena del radar
y calculando pérdidas de detección por vuelo.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import json


@dataclass
class FlightAnalysis:
    """Información de vuelo y análisis de pérdidas."""
    squawk_code: str  # Formato octal
    squawk_decimal: int
    flight_count: int
    antenna_rotation_speed: float  # RPM (revoluciones por minuto)
    scan_time_seconds: float  # Tiempo de un barrido (360°)
    confidence_score: float  # Puntuación de confianza
    
    # Métricas para Radar (basado en rotación)
    detection_probability: Optional[float] = None
    loss_per_scan: Optional[float] = None
    total_losses: Optional[float] = None
    average_detection_rate: Optional[float] = None

    # Métricas para ADS-B (basado en intervalo de actualización)
    avg_update_interval: Optional[float] = None
    max_update_interval: Optional[float] = None

    def to_dict(self):
        """Convierte a diccionario."""
        return asdict(self)


class FlightLossAnalyzer:
    """Analizador de vuelos, Squawk y pérdidas por rotación de antena."""
    
    def __init__(self, antenna_rpm: float = 12.0):
        """
        Inicializa el analizador.
        
        Args:
            antenna_rpm: RPM de la antena del radar (default: 12 RPM)
        """
        self.antenna_rpm = antenna_rpm
        self.scan_time = 60.0 / antenna_rpm  # Segundos por vuelta de 360°
        self.squawk_records = defaultdict(list)
        self.flight_analysis = {}
        self.statistics = {
            "total_records": 0,
            "unique_squawks": 0,
            "average_records_per_squawk": 0.0,
            "total_estimated_losses": 0.0,
            "total_flights": 0,
            "highest_loss_squawk": None,
            "lowest_loss_squawk": None
        }
    
    def update_antenna_speed(self, antenna_rpm: float):
        """Actualiza la velocidad de la antena."""
        self.antenna_rpm = antenna_rpm
        self.scan_time = 60.0 / antenna_rpm
        print(f"[*] Antenna speed updated: {antenna_rpm} RPM (scan time: {self.scan_time:.2f}s)")
    
    def analyze_records(self, records: List[Dict[str, Any]], is_adsb_only: bool = False) -> Dict[str, FlightAnalysis]:
        """
        Analiza registros y agrupa por código Squawk.
        
        Args:
            records: Lista de registros ASTERIX decodificados
            
        Returns:
            Diccionario de análisis por Squawk
        """
        # Limpiar análisis anterior
        self.squawk_records.clear()
        self.flight_analysis.clear()
        
        # Agrupar por Squawk
        for record in records:
            # Usar Mode S como fallback para ADS-B si no hay squawk
            squawk_code = record.get('mode_3a') or record.get('mode_s')
            if squawk_code is not None:
                squawk_octal = f"{squawk_code:04o}"
                self.squawk_records[squawk_octal].append(record)
        
        # Analizar cada Squawk
        for squawk_octal, records_list in self.squawk_records.items():
            self.flight_analysis[squawk_octal] = self._analyze_squawk(
                squawk_octal, records_list, is_adsb_only
            )
        
        # Actualizar estadísticas
        self._update_statistics()
        
        return self.flight_analysis
    
    def _analyze_squawk(self, squawk_octal: str, records: List[Dict], is_adsb_only: bool) -> FlightAnalysis:
        """
        Analiza registros de un código Squawk específico.
        
        Args:
            squawk_octal: Código Squawk en formato octal
            records: Lista de registros para este Squawk
            
        Returns:
            FlightAnalysis con información de pérdidas
        """
        squawk_decimal = int(squawk_octal, 8)
        flight_count = len(records)
        
        # Puntuación de confianza (basada en cantidad de registros)
        confidence_score = min(1.0, flight_count / 100.0)

        analysis = FlightAnalysis(
            squawk_code=squawk_octal,
            squawk_decimal=squawk_decimal,
            flight_count=flight_count,
            antenna_rotation_speed=self.antenna_rpm,
            scan_time_seconds=self.scan_time,
            confidence_score=confidence_score
        )

        if is_adsb_only:
            # Análisis para ADS-B: Intervalo de actualización
            timestamps = sorted([r['timestamp'] for r in records if r.get('timestamp') is not None])
            if len(timestamps) > 1:
                intervals = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
                analysis.avg_update_interval = sum(intervals) / len(intervals)
                analysis.max_update_interval = max(intervals)
            else:
                analysis.avg_update_interval = 0.0
                analysis.max_update_interval = 0.0
        else:
            # Análisis para Radar: Pérdidas por rotación
            # Detección base
            detection_probability = 0.95
            
            # Calcular pérdidas
            # La pérdida por barrido depende del tiempo de integración del radar
            # En general: pérdida ≈ (tiempo_integración / tiempo_barrido) * (1 - prob_detección)
            loss_per_scan = (1.0 / self.scan_time) * (1.0 - detection_probability) if self.scan_time > 0 else 0
            total_losses = loss_per_scan * flight_count
            
            # Tasa de detección promedio considerando velocidad de rotación
            # A mayor RPM, menos tiempo de integración por objetivo
            average_detection_rate = detection_probability * (1.0 - (loss_per_scan / flight_count)) if flight_count > 0 else 0
            
            analysis.detection_probability = detection_probability
            analysis.loss_per_scan = loss_per_scan
            analysis.total_losses = total_losses
            analysis.average_detection_rate = average_detection_rate

        return analysis
    
    def _update_statistics(self):
        """Actualiza estadísticas generales."""
        if not self.flight_analysis:
            return
        
        total_records = sum(analysis.flight_count for analysis in self.flight_analysis.values())
        
        # Las pérdidas solo se calculan para análisis tipo radar
        radar_analyses = [a for a in self.flight_analysis.values() if a.total_losses is not None]
        total_losses = sum(analysis.total_losses for analysis in radar_analyses)
        
        self.statistics.update({
            "total_records": total_records,
            "unique_squawks": len(self.flight_analysis),
            "average_records_per_squawk": total_records / len(self.flight_analysis) if self.flight_analysis else 0,
            "total_estimated_losses": total_losses,
            "total_flights": len(self.flight_analysis),
        })
        
        # Encontrar Squawk con mayor/menor pérdida
        if radar_analyses:
            highest = max(radar_analyses, key=lambda x: x.total_losses)
            lowest = min(radar_analyses, key=lambda x: x.total_losses)
            self.statistics["highest_loss_squawk"] = f"{highest.squawk_code} ({highest.total_losses:.4f})"
            self.statistics["lowest_loss_squawk"] = f"{lowest.squawk_code} ({lowest.total_losses:.4f})"
    
    def display_flight_summary(self, is_adsb_only: bool = False):
        """Muestra resumen de vuelos por Squawk."""
        if is_adsb_only:
            print(f"\n{'='*80}")
            print(f"FLIGHT ANALYSIS BY SQUAWK/MODE-S (ADS-B DATA)")
            print(f"{'='*80}\n")
            print(f"{'Squawk/ID':<12} {'Flights':<10} {'Avg Interval(s)':<18} {'Max Interval(s)':<18} {'Confidence':<12}")
            print("-" * 80)
        else:
            print(f"\n{'='*80}")
            print(f"FLIGHT ANALYSIS BY SQUAWK CODE (RADAR DATA)")
            print(f"Antenna Speed: {self.antenna_rpm} RPM | Scan Time: {self.scan_time:.2f}s")
            print(f"{'='*80}\n")
            print(f"{'Squawk':<12} {'Flights':<10} {'Loss/Scan':<12} "
                  f"{'Total Loss':<12} {'Det.Rate':<10} {'Confidence':<12}")
            print("-" * 80)
        
        for squawk_code in sorted(self.flight_analysis.keys()):
            analysis = self.flight_analysis[squawk_code]
            if is_adsb_only:
                print(f"{analysis.squawk_code:<12} {analysis.flight_count:<10} "
                      f"{analysis.avg_update_interval:<18.2f} "
                      f"{analysis.max_update_interval:<18.2f} "
                      f"{analysis.confidence_score:<12.2%}")
            else:
                print(f"{analysis.squawk_code:<12} {analysis.flight_count:<10} "
                      f"{analysis.loss_per_scan:<12.6f} "
                      f"{analysis.total_losses:<12.4f} "
                      f"{analysis.average_detection_rate:<10.2%} "
                      f"{analysis.confidence_score:<12.2%}")
        
        print("\n" + "="*80)
    
    def display_detailed_analysis(self, squawk_code: Optional[str] = None):
        """Muestra análisis detallado de un Squawk específico."""
        if squawk_code and squawk_code in self.flight_analysis:
            analyses = [self.flight_analysis[squawk_code]]
        else:
            analyses = list(self.flight_analysis.values())
        
        for analysis in analyses:
            print(f"\n{'='*70}")
            print(f"SQUAWK: {analysis.squawk_code} (Decimal: {analysis.squawk_decimal})")
            print(f"{'='*70}\n")
            
            print(f"Flight Information:")
            print(f"  Total Flight Records: {analysis.flight_count}")
            print(f"  Antenna Rotation Speed: {analysis.antenna_rotation_speed} RPM")
            print(f"  Scan Time (360°): {analysis.scan_time_seconds:.2f} seconds")
            
            print(f"\nDetection Analysis:")
            print(f"  Base Detection Probability: {analysis.detection_probability:.2%}")
            print(f"  Loss per Antenna Scan: {analysis.loss_per_scan:.6f}")
            print(f"  Total Estimated Losses: {analysis.total_losses:.4f}")
            print(f"  Average Detection Rate: {analysis.average_detection_rate:.2%}")
            
            print(f"\nConfidence Metrics:")
            print(f"  Confidence Score: {analysis.confidence_score:.2%}")
            print(f"  Data Quality: {'HIGH' if analysis.confidence_score > 0.75 else 'MEDIUM' if analysis.confidence_score > 0.5 else 'LOW'}")
            
            print(f"{'='*70}\n")
    
    def display_statistics(self):
        """Muestra estadísticas generales."""
        print(f"\n{'='*70}")
        print(f"GENERAL STATISTICS - FLIGHT ANALYSIS")
        print(f"{'='*70}\n")
        
        print(f"Total Records Analyzed: {self.statistics['total_records']}")
        print(f"Unique Squawk Codes: {self.statistics['unique_squawks']}")
        print(f"Average Records per Squawk: {self.statistics['average_records_per_squawk']:.2f}")
        print(f"Total Flights (Unique Squawks): {self.statistics['total_flights']}")
        
        print(f"\nLoss Analysis:")
        print(f"  Total Estimated Losses: {self.statistics['total_estimated_losses']:.4f}")
        print(f"  Highest Loss Squawk: {self.statistics['highest_loss_squawk']}")
        print(f"  Lowest Loss Squawk: {self.statistics['lowest_loss_squawk']}")
        
        print(f"\nRadar Configuration:")
        print(f"  Antenna Speed: {self.antenna_rpm} RPM")
        print(f"  Scan Period: {self.scan_time:.2f} seconds per 360°")
        
        print(f"{'='*70}\n")
    
    def get_top_squawks(self, limit: int = 10, sort_by: str = "flights") -> List[FlightAnalysis]:
        """
        Obtiene los Squawk principales.
        
        Args:
            limit: Cantidad de Squawk a retornar
            sort_by: Campo para ordenar ("flights", "losses", "confidence", "max_interval")
            
        Returns:
            Lista de FlightAnalysis ordenada
        """
        analyses = list(self.flight_analysis.values())
        
        if sort_by == "losses":
            analyses.sort(key=lambda x: x.total_losses or 0, reverse=True)
        elif sort_by == "confidence":
            analyses.sort(key=lambda x: x.confidence_score, reverse=True)
        elif sort_by == "max_interval":
            analyses.sort(key=lambda x: x.max_update_interval or 0, reverse=True)
        else:  # flights (default)
            analyses.sort(key=lambda x: x.flight_count, reverse=True)
        
        return analyses[:limit]
    
    def display_top_squawks(self, limit: int = 10, sort_by: str = "flights"):
        """Muestra los Squawk principales."""
        top_squawks = self.get_top_squawks(limit, sort_by)
        
        is_adsb_only = any(a.avg_update_interval is not None for a in top_squawks)

        sort_label = {
            "flights": "by Flight Count",
            "losses": "by Estimated Losses",
            "confidence": "by Confidence Score",
            "max_interval": "by Max Update Interval"
        }.get(sort_by, "by Flight Count")
        
        print(f"\n{'='*70}")
        print(f"TOP {limit} SQUAWKS/IDS - {sort_label.upper()}")
        print(f"{'='*70}\n")
        
        if is_adsb_only:
            print(f"{'Rank':<6} {'Squawk/ID':<12} {'Flights':<10} {'Avg Interval':<15} {'Max Interval':<15}")
            print("-" * 70)
            for idx, analysis in enumerate(top_squawks, 1):
                print(f"{idx:<6} {analysis.squawk_code:<12} {analysis.flight_count:<10} "
                      f"{analysis.avg_update_interval or 0:<15.2f} "
                      f"{analysis.max_update_interval or 0:<15.2f}")
        else:
            print(f"{'Rank':<6} {'Squawk':<12} {'Flights':<10} {'Losses':<12} {'Det.Rate':<12}")
            print("-" * 70)
            for idx, analysis in enumerate(top_squawks, 1):
                print(f"{idx:<6} {analysis.squawk_code:<12} {analysis.flight_count:<10} "
                      f"{analysis.total_losses or 0:<12.4f} {analysis.average_detection_rate or 0:<12.2%}")
        
        print(f"{'='*70}\n")
    
    def export_to_json(self, filename: str = "flight_analysis.json"):
        """Exporta análisis a JSON."""
        data = {
            "metadata": {
                "antenna_rpm": self.antenna_rpm,
                "scan_time_seconds": self.scan_time,
                "analysis_type": "Flight Analysis by Squawk"
            },
            "statistics": self.statistics.copy(),
            "analysis": {
                squawk: analysis.to_dict()
                for squawk, analysis in self.flight_analysis.items()
            }
        }
        
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            print(f"[OK] Analysis exported to {filename}")
        except Exception as e:
            print(f"[ERROR] Error exporting to {filename}: {e}")
    
    def export_to_csv(self, filename: str = "flight_analysis.csv"):
        """Exporta análisis a CSV."""
        try:
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow([
                    "Squawk_Octal",
                    "Squawk_Decimal",
                    "Flight_Count",
                    "Antenna_RPM",
                    "Scan_Time_Seconds",
                    "Detection_Probability",
                    "Loss_Per_Scan",
                    "Total_Losses",
                    "Average_Detection_Rate",
                    "Confidence_Score"
                ])
                
                # Data
                for squawk_code in sorted(self.flight_analysis.keys()):
                    analysis = self.flight_analysis[squawk_code]
                    writer.writerow([
                        analysis.squawk_code,
                        analysis.squawk_decimal,
                        analysis.flight_count,
                        analysis.antenna_rotation_speed,
                        f"{analysis.scan_time_seconds:.4f}",
                        f"{analysis.detection_probability:.4f}",
                        f"{analysis.loss_per_scan:.6f}",
                        f"{analysis.total_losses:.6f}",
                        f"{analysis.average_detection_rate:.4f}",
                        f"{analysis.confidence_score:.4f}"
                    ])
            
            print(f"[OK] Analysis exported to {filename}")
        except Exception as e:
            print(f"[ERROR] Error exporting to {filename}: {e}")


def main():
    """Ejemplo de uso."""
    # Datos de ejemplo
    sample_records = [
        {"mode_3a": 0o7654, "flight_level": 25000},
        {"mode_3a": 0o7654, "flight_level": 25500},
        {"mode_3a": 0o7654, "flight_level": 24500},
        {"mode_3a": 0o1234, "flight_level": 15000},
        {"mode_3a": 0o1234, "flight_level": 15500},
        {"mode_3a": 0o5555, "flight_level": 35000},
    ] * 5  # Repetir para simular más datos
    
    analyzer = FlightLossAnalyzer(antenna_rpm=12.0)
    analyzer.analyze_records(sample_records)
    
    # Mostrar resultados
    analyzer.display_flight_summary()
    analyzer.display_statistics()
    analyzer.display_top_squawks(limit=5, sort_by="flights")
    analyzer.display_top_squawks(limit=5, sort_by="losses")
    
    # Mostrar detallado
    analyzer.display_detailed_analysis()
    
    # Exportar
    analyzer.export_to_json("flight_analysis_example.json")
    analyzer.export_to_csv("flight_analysis_example.csv")


if __name__ == "__main__":
    main()
