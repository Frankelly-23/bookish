<div class="cover-page">
  <img src="logo.jpeg" alt="Universidad Central del Este" class="cover-logo" />
  <h2>Facultad de Ciencias e Ingenierías</h2>
  <h3>Escuela de Ingeniería de Software</h3>

  <p><strong>Asignatura:</strong> ISW-123-1</p>
  <p><strong>Asignación:</strong> Práctica 2. Registro de Empleados</p>
  <p><strong>Estudiante:</strong> Frankelly Cordero</p>
  <p><strong>Matrícula:</strong> 2024-3153</p>
  <p><strong>Fecha Límite:</strong> martes, 4 de agosto de 2026, 20:00</p>
</div>

### Introducción

En esta práctica se implementan los modificadores de acceso de C# dentro de un sistema orientado a objetos que usa **herencia**. Se creó la clase base `Cliente` y la clase derivada `Empleado`, junto con el formulario *Registro de Empleados* que permite **Guardar, Buscar, Actualizar y Eliminar** empleados. El objetivo es demostrar cómo `protected`, `private`, `public` y `protected internal` protegen los datos según el nivel de exposición deseado.

### Modificadores de acceso utilizados

| Modificador | Miembro | Justificación |
|---|---|---|
| `protected` | `codigo`, `nombre`, `apellido`, `cedula` en `Cliente` | Se heredan a `Empleado`, que debe leerlos/escribirlos, pero el exterior no debe tocarlos directamente. |
| `protected internal` | `departamento` en `Cliente` | Compartido entre las clases del proyecto y heredado por `Empleado`. |
| `private` | `contrasena` en `Cliente`; `cargo`, `salario`, `fechaIngreso` en `Empleado` | Datos sensibles: solo accesibles dentro de su propia clase. |
| `public` | Propiedades y métodos del formulario (`Guardar`, `Buscar`, `Actualizar`, `Eliminar`) | Requisito de la práctica: los métodos que usa el formulario son públicos. |

### Implementación

**1. Clase base `Cliente`** con atributos `protected` y `protected internal`:

```csharp
public class Cliente
{
    // protected: atributos heredados por Empleado
    protected string codigo;
    protected string nombre;
    protected string apellido;
    protected string cedula;

    // protected internal: compartido entre clases del proyecto y heredado
    protected internal string departamento;

    // private: dato sensible
    private string contrasena;

    public Cliente() { }

    public Cliente(string codigo, string nombre, string apellido, string cedula, string departamento)
    {
        this.codigo = codigo;
        this.nombre = nombre;
        this.apellido = apellido;
        this.cedula = cedula;
        this.departamento = departamento;
    }

    // public: el formulario necesita leer/modificar estos datos heredados
    public string Codigo { get { return codigo; } set { codigo = value; } }
    public string Nombre { get { return nombre; } set { nombre = value; } }
    public string Apellido { get { return apellido; } set { apellido = value; } }
    public string Cedula { get { return cedula; } set { cedula = value; } }
    public string Departamento { get { return departamento; } set { departamento = value; } }
}
```

**2. Clase derivada `Empleado : Cliente`** (herencia simple, reutiliza el constructor de la base):

```csharp
public class Empleado : Cliente
{
    // private: datos sensibles del empleado
    private string cargo;
    private decimal salario;
    private DateTime fechaIngreso;

    public Empleado() : base() { }

    public Empleado(string codigo, string nombre, string apellido, string cedula,
                    string departamento, string cargo, decimal salario, DateTime fechaIngreso)
        : base(codigo, nombre, apellido, cedula, departamento)
    {
        this.cargo = cargo;
        this.salario = salario;
        this.fechaIngreso = fechaIngreso;
    }

    // public: metodos usados por el formulario
    public string Cargo { get { return cargo; } set { cargo = value; } }
    public decimal Salario { get { return salario; } set { salario = value; } }
    public DateTime FechaIngreso { get { return fechaIngreso; } set { fechaIngreso = value; } }
}
```

**3. Formulario `EmpleadosForm`**: los botones llaman a métodos `public` que usan el objeto `Empleado` para interactuar con la base de datos, y los datos se muestran en un `DataGridView`.

```csharp
// public: metodo del formulario. Crea un objeto Empleado (herencia) y lo guarda.
public void Guardar()
{
    if (!ValidarCampos()) return;
    decimal salario = 0m;
    if (!decimal.TryParse(txtSalario.Text.Replace(",", "."), out salario)) salario = 0m;

    Empleado emp = new Empleado(
        txtCodigo.Text.Trim(), txtNombre.Text.Trim(), txtApellido.Text.Trim(),
        txtCedula.Text.Trim(), txtDepartamento.Text.Trim(), txtCargo.Text.Trim(),
        salario, dtpFechaIngreso.Value);

    string sql = $"INSERT INTO Empleados (Codigo, Nombre, Apellido, Cedula, Cargo, Departamento, Salario, Fecha_Ingreso) " +
        $"VALUES ('{Utilidades.SanitizarSQL(emp.Codigo)}','{Utilidades.SanitizarSQL(emp.Nombre)}','{Utilidades.SanitizarSQL(emp.Apellido)}'," +
        $"'{Utilidades.SanitizarSQL(emp.Cedula)}','{Utilidades.SanitizarSQL(emp.Cargo)}','{Utilidades.SanitizarSQL(emp.Departamento)}'," +
        $"{emp.Salario.ToString("F2").Replace(",", ".")},'{emp.FechaIngreso:yyyy-MM-dd}')";
    if (db.EjecutarComando(sql))
    {
        lblResultado.Text = "Empleado guardado.";
        CargarDatos();
        LimpiarCampos();
    }
}
```

```csharp
// protected override: polimorfismo sobre el metodo de BaseForm.
protected override void CargarDatos()
{
    DataTable dt = db.EjecutarConsulta("SELECT * FROM Empleados");
    if (dt != null) dgvDatos.DataSource = dt;
}
```
### Captura:

<img src="captura_registro_empleados.png" alt="Captura del formulario Registro de Empleados" class="screenshot" />