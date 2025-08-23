$siteUrl = "https://sortsactivedev.sharepoint.com/sites/prueba"
$adminUrl = "https://sortsactivedev-admin.sharepoint.com"

Clear-Host

    #Este script es para generar un certificado autofirmado y exportarlo a PFX y CER que luego se usará en la app de Python de Azure


    try {

        Connect-PnPOnline -Url $adminUrl -UseWebLogin

        #Get-PnPTenant | Select DisableCustomAppAuthentication

        # Crear un certificado autofirmado (válido 2 a?os)
        $cert = New-SelfSignedCertificate -CertStoreLocation Cert:\CurrentUser\My -Subject "CN=MiAppSharePointPython" -KeyExportPolicy Exportable -KeySpec Signature -NotAfter (Get-Date).AddYears(2)

        # Exportar la clave privada a un archivo PFX
        $pwd = ConvertTo-SecureString -String "MiPasswordSegura123" -Force -AsPlainText
        Export-PfxCertificate -Cert $cert -FilePath "C:\repositorio\examples\pySharepoint\MiAppSharePointPython.pfx" -Password $pwd

        # Exportar certificado público
        Export-Certificate -Cert $cert -FilePath "C:\repositorio\examples\pySharepoint\MiAppSharePointPython.cer"

        Get-PfxCertificate -FilePath "C:\repositorio\examples\pySharepoint\MiAppSharePointPython.cer"

        #Thumbprint                                Subject              EnhancedKeyUsageList
        #----------                                -------              --------------------
        #A2C0322C559E3D70C69FB96A27C76479E7EF22C9  CN=MiAppSharePointP… {Autenticación del cliente, Autenticación del servidor}

        Disconnect-PnPOnline

    }
    catch {
       
       
    }    




