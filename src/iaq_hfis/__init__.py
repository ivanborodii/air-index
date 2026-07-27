"""iaq_hfis: hierarchical fuzzy indoor air quality index.

Reference implementation of the two-level Mamdani fuzzy-logic method
described in Borodii & Osukhivska, "Ієрархічний нечіткий метод формування
інтегральної оцінки якості повітря у приміщенні на основі сенсорних
вимірювань". Reads sensor data produced by the separate ``air-monitor``
collection pipeline and never modifies it.
"""

__version__ = "0.1.0"
