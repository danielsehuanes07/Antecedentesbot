from app import clasificar_resultado, normalizar


def test_normalizar_quita_tildes_y_espacios():
    assert normalizar("  cédula   válida ") == "CEDULA VALIDA"


def test_clasifica_sin_asuntos_pendientes():
    assert (
        clasificar_resultado("NO TIENE ASUNTOS PENDIENTES CON LAS AUTORIDADES JUDICIALES")
        == "sin_asuntos_pendientes"
    )


def test_clasifica_no_requerido():
    assert clasificar_resultado("ACTUALMENTE NO ES REQUERIDO POR AUTORIDAD JUDICIAL") == "no_requerido"


def test_clasifica_texto_desconocido():
    assert clasificar_resultado("respuesta nueva") == "resultado_no_reconocido"
