#!/usr/bin/env python3
"""
Mode A/C Detection Analyzer

Módulo para extraer y analizar información de Modo A (con FL), Modo C, 
código Squawk y probabilidades de detección desde paquetes ASTERIX decodificados.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import json


@dataclass
class ModeDetection:
    """Información de detección por modo."""
    mode_a_detected: bool
    mode_c_detected: bool
    squawk_code: Optional[int] = None
    flight_level: Optional[int] = None
    mode_3a: Optional[int] = None
    mode_a_probability: float = 0.0
    mode_c_probability: float = 0.0
    combined_probability: Optional[float] = None
    confidence_level: str = "unknown"  # low, medium, high
    
    def to_dict(self):
        """Convierte a diccionario."""
        return asdict(self)


class ModeAnalyzer:
    """Analizador de modos A/C y probabilidades de detección."""
    
    def __init__(self):
        self.detections = []
        self.statistics = {
            "total_records": 0,
            "mode_a_only": 0,
            "mode_c_only": 0,
            "mode_a_and_c": 0,
            "no_mode_data": 0,
            "average_mode_a_probability": 0.0,
            "average_mode_c_probability": 0.0,
            "average_combined_probability": 0.0,
            "squawk_codes_found": set(),
            "flight_levels_found": []
        }
    
    def analyze_record(self, record: Dict[str, Any]) -> ModeDetection:
        """
        Analiza un registro decodificado y extrae información de Modo A/C.
        
        Args:
            record: Diccionario con datos del registro decodificado
            
        Returns:
            ModeDetection con información extraída
        """
        self.statistics["total_records"] += 1
        
        # Extraer información de modo A (Mode 3/A Code)
        mode_3a = record.get('mode_3a')
        mode_a_detected = mode_3a is not None and mode_3a != 0xFFF
        
        # Extraer Flight Level (información asociada a Modo A)
        flight_level = record.get('flight_level')
        
        # El Modo C se considera presente si hay Modo 3/A con Flight Level
        mode_c_detected = mode_a_detected and flight_level is not None
        
        # Squawk es el código Mode 3/A
        squawk_code = mode_3a if mode_a_detected else None
        
        # Calcular probabilidades basadas en disponibilidad de datos
        mode_a_probability = 0.95 if mode_a_detected else 0.0
        mode_c_probability = 0.90 if mode_c_detected else 0.0
        
        # Probabilidad combinada si ambos están presentes
        combined_probability = None
        if mode_a_detected and mode_c_detected:
            # Combinar probabilidades: P(A AND C) = P(A) * P(C|A)
            combined_probability = mode_a_probability * mode_c_probability
            self.statistics["mode_a_and_c"] += 1
        elif mode_a_detected:
            self.statistics["mode_a_only"] += 1
        elif mode_c_detected:
            self.statistics["mode_c_only"] += 1
        else:
            self.statistics["no_mode_data"] += 1
        
        # Determinar nivel de confianza
        confidence_level = self._calculate_confidence(
            mode_a_detected, mode_c_detected, flight_level
        )
        
        # Crear objeto de detección
        detection = ModeDetection(
            mode_a_detected=mode_a_detected,
            mode_c_detected=mode_c_detected,
            squawk_code=squawk_code,
            flight_level=flight_level,
            mode_3a=mode_3a,
            mode_a_probability=mode_a_probability,
            mode_c_probability=mode_c_probability,
            combined_probability=combined_probability,
            confidence_level=confidence_level
        )
        
        # Registrar información
        self.detections.append(detection)
        if squawk_code:
            self.statistics["squawk_codes_found"].add(squawk_code)
        if flight_level:
            self.statistics["flight_levels_found"].append(flight_level)
        
        return detection
    
    def _calculate_confidence(self, mode_a: bool, mode_c: bool, 
                             flight_level: Optional[int]) -> str:
        """Calcula el nivel de confianza en la detección."""
        if mode_a and mode_c and flight_level is not None:
            return "high"
        elif mode_a and flight_level is not None:
            return "medium"
        elif mode_a:
            return "medium"
        else:
            return "low"
    
    def analyze_batch(self, records: List[Dict[str, Any]]) -> List[ModeDetection]:
        """
        Analiza un lote de registros.
        
        Args:
            records: Lista de registros decodificados
            
        Returns:
            Lista de ModeDetection
        """
        results = []
        for record in records:
            results.append(self.analyze_record(record))
        
        self._update_statistics()
        return results
    
    def _update_statistics(self):
        """Actualiza estadísticas generales."""
        if not self.detections:
            return
        
        # Convertir squawk codes a lista
        self.statistics["squawk_codes_found"] = sorted(
            list(self.statistics["squawk_codes_found"])
        )
        
        # Calcular promedios
        mode_a_probs = [d.mode_a_probability for d in self.detections if d.mode_a_probability > 0]
        mode_c_probs = [d.mode_c_probability for d in self.detections if d.mode_c_probability > 0]
        combined_probs = [d.combined_probability for d in self.detections 
                          if d.combined_probability is not None]
        
        if mode_a_probs:
            self.statistics["average_mode_a_probability"] = sum(mode_a_probs) / len(mode_a_probs)
        
        if mode_c_probs:
            self.statistics["average_mode_c_probability"] = sum(mode_c_probs) / len(mode_c_probs)
        
        if combined_probs:
            self.statistics["average_combined_probability"] = sum(combined_probs) / len(combined_probs)
    
    def display_single_record(self, detection: ModeDetection, record_idx: int = 0):
        """Muestra información de un registro individual."""
        print(f"\n{'='*70}")
        print(f"RECORD #{record_idx + 1} - MODE A/C ANALYSIS")
        print(f"{'='*70}")
        
        print(f"\nMode A (3/A Code):")
        print(f"  Detected: {'YES' if detection.mode_a_detected else 'NO'}")
        if detection.squawk_code is not None:
            print(f"  Squawk Code: {detection.squawk_code:04o} (octal) / {detection.squawk_code} (decimal)")
        print(f"  Probability: {detection.mode_a_probability:.2%}")
        
        print(f"\nMode C (Flight Level):")
        print(f"  Detected: {'YES' if detection.mode_c_detected else 'NO'}")
        if detection.flight_level is not None:
            print(f"  Flight Level: FL{detection.flight_level}")
        print(f"  Probability: {detection.mode_c_probability:.2%}")
        
        print(f"\nCombined Detection (Mode A + Mode C):")
        if detection.combined_probability is not None:
            print(f"  P(A AND C): {detection.combined_probability:.2%}")
        else:
            print(f"  P(A AND C): N/A (Both modes not present)")
        
        print(f"\nConfidence Level: {detection.confidence_level.upper()}")
        print(f"{'='*70}\n")
    
    def display_statistics(self):
        """Muestra estadísticas generales."""
        print(f"\n{'='*70}")
        print(f"MODE A/C DETECTION STATISTICS")
        print(f"{'='*70}\n")
        
        print(f"Total Records Analyzed: {self.statistics['total_records']}")
        print(f"  - Mode A Only: {self.statistics['mode_a_only']}")
        print(f"  - Mode C Only: {self.statistics['mode_c_only']}")
        print(f"  - Mode A AND C: {self.statistics['mode_a_and_c']}")
        print(f"  - No Mode Data: {self.statistics['no_mode_data']}")
        
        print(f"\nAverage Probabilities:")
        print(f"  - Mode A: {self.statistics['average_mode_a_probability']:.2%}")
        print(f"  - Mode C: {self.statistics['average_mode_c_probability']:.2%}")
        if self.statistics['average_combined_probability'] > 0:
            print(f"  - Combined (A AND C): {self.statistics['average_combined_probability']:.2%}")
        
        print(f"\nSquawk Codes Found: {len(self.statistics['squawk_codes_found'])}")
        if self.statistics['squawk_codes_found']:
            codes_display = ', '.join(f"{c:04o}" for c in self.statistics['squawk_codes_found'][:10])
            if len(self.statistics['squawk_codes_found']) > 10:
                codes_display += "..."
            print(f"  {codes_display}")
        
        print(f"\nFlight Levels Found: {len(self.statistics['flight_levels_found'])}")
        if self.statistics['flight_levels_found']:
            fl_unique = sorted(set(self.statistics['flight_levels_found']))
            fl_display = ', '.join(f"FL{fl}" for fl in fl_unique[:10])
            if len(fl_unique) > 10:
                fl_display += "..."
            print(f"  {fl_display}")
        
        print(f"{'='*70}\n")
    
    def export_to_json(self, filename: str = "mode_analysis.json"):
        """Exporta resultados a JSON."""
        data = {
            "statistics": self.statistics.copy(),
            "statistics": {
                **self.statistics,
                "squawk_codes_found": list(self.statistics["squawk_codes_found"]),
                "flight_levels_found": sorted(set(self.statistics["flight_levels_found"]))
            },
            "detections": [d.to_dict() for d in self.detections]
        }
        
        # Convertir Combined probability a string si es None
        for det in data["detections"]:
            if det["combined_probability"] is not None:
                det["combined_probability"] = float(det["combined_probability"])
        
        try:
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            print(f"[✓] Analysis exported to {filename}")
        except Exception as e:
            print(f"[✗] Error exporting to {filename}: {e}")
    
    def export_to_csv(self, filename: str = "mode_analysis.csv"):
        """Exporta resultados a CSV."""
        try:
            import csv
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow([
                    "Record#",
                    "Mode_A_Detected",
                    "Mode_C_Detected",
                    "Squawk_Code",
                    "Squawk_Octal",
                    "Flight_Level",
                    "Mode_A_Probability",
                    "Mode_C_Probability",
                    "Combined_Probability",
                    "Confidence_Level"
                ])
                
                # Data
                for idx, det in enumerate(self.detections, 1):
                    squawk_octal = f"{det.squawk_code:04o}" if det.squawk_code else ""
                    writer.writerow([
                        idx,
                        det.mode_a_detected,
                        det.mode_c_detected,
                        det.squawk_code or "",
                        squawk_octal,
                        det.flight_level or "",
                        f"{det.mode_a_probability:.4f}",
                        f"{det.mode_c_probability:.4f}",
                        f"{det.combined_probability:.4f}" if det.combined_probability else "",
                        det.confidence_level
                    ])
            
            print(f"[✓] Analysis exported to {filename}")
        except Exception as e:
            print(f"[✗] Error exporting to {filename}: {e}")


def main():
    """Ejemplo de uso del analizador."""
    # Datos de ejemplo
    sample_records = [
        {
            "mode_3a": 0o7654,
            "flight_level": 25000,
            "category": 48
        },
        {
            "mode_3a": 0o1234,
            "flight_level": 15000,
            "category": 48
        },
        {
            "mode_3a": 0o0000,
            "flight_level": None,
            "category": 48
        }
    ]
    
    analyzer = ModeAnalyzer()
    results = analyzer.analyze_batch(sample_records)
    
    # Mostrar cada registro
    for idx, detection in enumerate(results):
        analyzer.display_single_record(detection, idx)
    
    # Mostrar estadísticas
    analyzer.display_statistics()
    
    # Exportar
    analyzer.export_to_json("mode_analysis_example.json")
    analyzer.export_to_csv("mode_analysis_example.csv")


if __name__ == "__main__":
    main()
